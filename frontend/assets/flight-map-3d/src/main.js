import * as THREE from 'three';
import { createScene } from './core/scene.js';
import { createCamera } from './core/camera.js';
import { createRenderer } from './core/renderer.js';
import { createLights } from './core/lights.js';
import { createControls } from './core/controls.js';
import { loadModel } from './loaders/modelLoader.js';
import { createPlaneTemplate } from './objects/plane.js';
import { createMapMesh } from './objects/mapMesh.js';
import { loadWeatherMeshKit } from './utils/cloudFactory.js';
import { createRouteInspector } from './utils/routeInspector.js';
import { applyExecutiveEnvironment } from './utils/executiveEnvironment.js';
import { createFlightHud } from './utils/flightHud.js';

import {
    alignAirportsToMap,
    createSceneDataGroup,
    disposeSceneDataGroup,
    renderAltitudeLegend,
    renderMeta,
    renderMetrics,
} from './sceneData.js';
import { checkBackendHealth, fetchSceneData, replanWeatherScene } from './services/routeService.js';

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

const container = document.getElementById('app');
const isMobileDevice = window.matchMedia('(max-width: 760px), (pointer: coarse)').matches;
const modelAssetUrl = file => `${import.meta.env.BASE_URL}models/${file}`;

// Gentle canvas fade-in once the first scenario is on screen.
const bootStyle = document.createElement('style');
bootStyle.textContent = '#app{opacity:0;transition:opacity 1s ease}body.scene-ready #app{opacity:1}';
document.head.appendChild(bootStyle);

const scene = createScene();
const camera = createCamera();
const renderer = createRenderer(container, scene, camera);
const controls = createControls(camera, renderer.domElement);
createLights(scene);
applyExecutiveEnvironment(scene);

// Camera sits on the SOUTH side of the corridor, looking north — the scene
// reads like a conventional map (Craiova south, Cluj-Napoca north).
const cameraOffset = new THREE.Vector3(0, 520, -720);

// Smooth camera glide state.
const cameraTween = {
    active: false,
    from: new THREE.Vector3(),
    to: new THREE.Vector3(),
    targetFrom: new THREE.Vector3(),
    targetTo: new THREE.Vector3(),
    t: 0,
    duration: 1.8,
};

function startCameraTween(targetPosition, targetLook) {
    cameraTween.from.copy(camera.position);
    cameraTween.to.copy(targetPosition);
    cameraTween.targetFrom.copy(controls.target);
    cameraTween.targetTo.copy(targetLook);
    cameraTween.t = 0;
    cameraTween.active = true;
    controls.enabled = false; // hands off while gliding
}

function cancelCameraTween() {
    if (!cameraTween.active) return;
    cameraTween.active = false;
    controls.enabled = true;
}

// User interaction always wins over the glide.
renderer.domElement.addEventListener('pointerdown', cancelCameraTween);
renderer.domElement.addEventListener('wheel', cancelCameraTween, { passive: true });

// ---------------------------------------------------------------------------
// Scenario state — ALL declarations live here, BEFORE anything that
// closes over them (inspector, HUD, loaders).
// ---------------------------------------------------------------------------

const scenarioSelector = document.getElementById('scenario-selector');
const status = document.getElementById('data-status');
const query = new URLSearchParams(window.location.search);

const scenarios = new Set([
    // Multi-airport / multi-aircraft showcase scenarios first.
    'crossroads-storm',
    'converge-bucharest',
    'carpathian-siege',
    // Single-corridor classics.
    'storm-wall',
    'over-the-top',
    'low-corridor',
    'slalom',
    'fuel-critical',
    'in-flight-replan',
    'real-meteo',
]);

const SCENARIO_TITLES = {
    'crossroads-storm': 'Storm crossroads — 3 aircraft',
    'converge-bucharest': 'Converge on Bucharest — 4 aircraft',
    'carpathian-siege': 'Carpathian siege — triangle flights',
    'storm-wall': 'Storm wall',
    'over-the-top': 'Over the top',
    'low-corridor': 'Low corridor',
    'slalom': 'Slalom',
    'fuel-critical': 'Fuel critical',
    'in-flight-replan': 'In-flight replan',
    'real-meteo': 'Real meteo (AIFS)',
};

const initialScenario = query.get('scenario') || 'crossroads-storm';

// Rebuild the <select> options from the scenario set so the markup can never
// drift from the backend's scenario list (a stale option list silently
// yields value="" — the cause of an earlier 404).
scenarioSelector.replaceChildren(
    ...[...scenarios].map(key => {
        const option = document.createElement('option');
        option.value = key;
        option.textContent = SCENARIO_TITLES[key] || key;
        return option;
    }),
);
scenarioSelector.value = scenarios.has(initialScenario) ? initialScenario : 'crossroads-storm';
if (!scenarioSelector.value) scenarioSelector.value = 'crossroads-storm'; // belt and braces

let activeDataGroup;
let activePayload;
let activePlaneTemplate;
let activeWeatherMeshKit;
let weatherUpdateTimer;
let weatherRenderTimer;
let weatherUpdateNumber = 0;
let mapMesh;
let groundSampler = null;
let requestId = 0;
let activeScenarioController;

const mapPromise = loadModel(modelAssetUrl(isMobileDevice ? 'romania-mobile.glb' : 'romania.glb'));
const planeTemplatePromise = createPlaneTemplate(
    isMobileDevice ? modelAssetUrl('plane-mobile.glb') : undefined,
);
const weatherKitPromise = loadWeatherMeshKit();

function setStatus(text) {
    if (status) status.textContent = text;
    const bootStatus = document.getElementById('boot-status');
    if (bootStatus && !document.body.classList.contains('scene-ready')) {
        bootStatus.textContent = text;
    }
}

function scheduleWeatherRender(payload, scenarioRequestId) {
    window.clearTimeout(weatherRenderTimer);
    if (!activeWeatherMeshKit) return;

    weatherRenderTimer = window.setTimeout(() => {
        if (scenarioRequestId !== requestId || activePayload !== payload) return;
        const progress = activeDataGroup && activeDataGroup.userData.getFlightProgress
            ? activeDataGroup.userData.getFlightProgress()
            : 0;
        applyScenePayload(payload, progress);
    }, 250);
}

weatherKitPromise.then(kit => {
    activeWeatherMeshKit = kit;
    if (activePayload) scheduleWeatherRender(activePayload, requestId);
}, error => {
    console.warn('Weather kit unavailable:', error);
});

// Report backend availability early so a dead server is obvious immediately.
checkBackendHealth().then(health => {
    if (!health.ok) setStatus(`Backend unavailable (${health.detail}) — retrying scenarios anyway…`);
});

// ---------------------------------------------------------------------------
// Click-to-inspect + live HUD — created AFTER the state declarations so
// their closures are always safe, even if a listener fires instantly.
// ---------------------------------------------------------------------------

const routeInspector = createRouteInspector({
    camera,
    domElement: renderer.domElement,
    getDataGroup: () => activeDataGroup,
    getPayload: () => activePayload,
    scene,
});

const flightHud = createFlightHud({
    getPlaneState: () => activeDataGroup && activeDataGroup.userData.getPlaneState
        ? activeDataGroup.userData.getPlaneState()
        : null,
    getPayload: () => activePayload,
});

/**
 * Terrain height sampler with a result cache. Waypoints repeat heavily
 * across routes and airports (shared endpoints, dense resampling), so the
 * cache eliminates most of the expensive full-mesh raycasts that used to
 * freeze the tab on every scenario load. Returns null when no map is loaded.
 */
function createGroundSampler(map) {
    if (!map) return null;

    map.updateWorldMatrix(true, true);
    const mapBounds = new THREE.Box3().setFromObject(map);
    const raycaster = new THREE.Raycaster();
    raycaster.far = mapBounds.getSize(new THREE.Vector3()).y + 4;
    const cache = new Map();

    return (x, z) => {
        const key = `${x.toFixed(1)}|${z.toFixed(1)}`;
        if (cache.has(key)) return cache.get(key);
        raycaster.ray.origin.set(x, mapBounds.max.y + 2, z);
        raycaster.ray.direction.set(0, -1, 0);
        const surface = raycaster.intersectObject(map, true)[0];
        const height = surface ? surface.point.y : null;
        cache.set(key, height);
        return height;
    };
}

// ---------------------------------------------------------------------------
// Scenario loading
// ---------------------------------------------------------------------------

async function loadScenario(routeProgress = 0.35) {
    const currentRequestId = ++requestId;
    if (activeScenarioController) activeScenarioController.abort();
    const scenarioController = new AbortController();
    activeScenarioController = scenarioController;
    const scenario = scenarioSelector.value;
    if (!scenario) {
        setStatus('No scenario selected.');
        return;
    }
    setStatus(`Loading ${scenario}…`);

    try {
        const payload = await (scenario === 'in-flight-replan' && activePayload
            ? replanWeatherScene(activePayload, routeProgress, undefined, scenarioController.signal)
            : fetchSceneData(scenario, routeProgress, scenarioController.signal));
        if (currentRequestId !== requestId) return;

        applyScenePayload(payload, 0, false);
        scheduleWeatherRender(payload, currentRequestId);
        const bootStatus = document.getElementById('boot-status');
        if (bootStatus) bootStatus.textContent = 'Scenario ready — preparing terrain and aircraft…';
        document.body.classList.add('scene-ready');

        const bounds = payload.meta && payload.meta.map_bounds;
        if (bounds) {
            const optimizedRoute = (payload.routes && payload.routes.optimized) || [];
            const routeAltitude = optimizedRoute.length
                ? optimizedRoute.reduce((total, waypoint) => total + waypoint.y, 0) / optimizedRoute.length
                : 0;
            const lookAt = new THREE.Vector3(
                (bounds.min_x + bounds.max_x) / 2,
                routeAltitude,
                (bounds.min_z + bounds.max_z) / 2,
            );
            startCameraTween(lookAt.clone().add(cameraOffset), lookAt);
        }

        // Terrain and aircraft are large/independent assets. Attach them when
        // ready, then rebuild once so terrain snapping and flight animation
        // use their final models without delaying the initial scene.
        const [mapResult, planeResult] = await Promise.allSettled([
            mapPromise,
            planeTemplatePromise,
        ]);
        if (currentRequestId !== requestId) return;

        if (!mapMesh) {
            if (mapResult.status === 'fulfilled') {
                const mapBounds = payload.meta && payload.meta.map_bounds;
                mapMesh = createMapMesh(mapResult.value, payload.grid, mapBounds);
                scene.add(mapMesh);
            } else {
                console.warn('Romania map unavailable:', mapResult.reason);
            }
        }

        if (mapMesh && !groundSampler) groundSampler = createGroundSampler(mapMesh);

        activePlaneTemplate = planeResult.status === 'fulfilled' ? planeResult.value : null;
        if (planeResult.status === 'rejected') console.warn('Aircraft model unavailable:', planeResult.reason);
        if (mapMesh || activePlaneTemplate) {
            applyScenePayload(payload, routeProgress, false);
            scheduleWeatherRender(payload, currentRequestId);
        }
        if (bootStatus) bootStatus.textContent = 'Scene ready.';

        scheduleWeatherUpdate();
    } catch (error) {
        if (currentRequestId === requestId) {
            console.error(`Failed to load ${scenario} scenario:`, error);
            setStatus(`Could not load ${scenario}: ${error.message}`);
        }
    } finally {
        if (activeScenarioController === scenarioController) activeScenarioController = undefined;
        document.body.classList.add('scene-ready');
    }
}

scenarioSelector.addEventListener('change', () => {
    window.clearTimeout(weatherUpdateTimer);
    const routeProgress = activeDataGroup && activeDataGroup.userData.getFlightProgress
        ? activeDataGroup.userData.getFlightProgress()
        : 0.35;
    const nextQuery = new URLSearchParams(window.location.search);
    nextQuery.set('scenario', scenarioSelector.value);
    window.history.replaceState(null, '', `${window.location.pathname}?${nextQuery}`);
    loadScenario(routeProgress);
});

function applyScenePayload(payload, initialProgress = 0, includeWeather = true) {
    // Clear any lingering inspection marker/panel from the previous scene.
    routeInspector.clear();

    const nextGroup = createSceneDataGroup(
        payload,
        activePlaneTemplate,
        initialProgress,
        includeWeather ? activeWeatherMeshKit : null,
        groundSampler,
        includeWeather,
    );
    if (activeDataGroup) {
        scene.remove(activeDataGroup);
        disposeSceneDataGroup(activeDataGroup);
    }
    activeDataGroup = nextGroup;
    activePayload = payload;
    scene.add(activeDataGroup);
    if (mapMesh) alignAirportsToMap(activeDataGroup, mapMesh);
    renderAltitudeLegend(payload.grid || []);
    renderMetrics((payload.routes && payload.routes.metrics) || {});
    renderMeta({
        ...payload.meta,
        event_count: (payload.events && payload.events.length) || 0,
    });
}

// ---------------------------------------------------------------------------
// Live weather updates (in-flight-replan scenario)
// ---------------------------------------------------------------------------

function scheduleWeatherUpdate() {
    window.clearTimeout(weatherUpdateTimer);
    if (scenarioSelector.value !== 'in-flight-replan' || !activePayload) return;

    const delay = 7000 + Math.random() * 8000;
    weatherUpdateTimer = window.setTimeout(runWeatherUpdate, delay);
}

async function runWeatherUpdate() {
    const previousPayload = activePayload;
    if (!previousPayload || scenarioSelector.value !== 'in-flight-replan') return;

    const progress = activeDataGroup && activeDataGroup.userData.getFlightProgress
        ? activeDataGroup.userData.getFlightProgress()
        : 0;
    const weatherSeed = Math.floor(Math.random() * 2147483647);
    const updateNumber = ++weatherUpdateNumber;
    setStatus(`Checking weather change ${updateNumber}…`);

    try {
        const nextPayload = await replanWeatherScene(previousPayload, progress, weatherSeed);
        if (activePayload !== previousPayload || scenarioSelector.value !== 'in-flight-replan') return;

        nextPayload.meta.trajectory_status = nextPayload.weather_update.replanned
            ? `Weather update ${updateNumber}: ${nextPayload.meta.trajectory_status}`
            : `Weather update ${updateNumber}: route unchanged below drastic threshold`;
        applyScenePayload(nextPayload, nextPayload.weather_update.replanned ? 0 : progress, false);
        scheduleWeatherRender(nextPayload, requestId);
    } catch (error) {
        console.error('Weather update failed:', error);
        setStatus(`Weather update failed: ${error.message}`);
    } finally {
        scheduleWeatherUpdate();
    }
}

// ---------------------------------------------------------------------------
// Flutter bridges
// ---------------------------------------------------------------------------

// Flutter can push scenario changes into the WebView.
window.addEventListener('message', event => {
    const data = event.data;
    if (!data || typeof data !== 'object') return;
    if (data.type === 'airspace:scenario' && typeof data.scenario === 'string' && scenarios.has(data.scenario)) {
        scenarioSelector.value = data.scenario;
        scenarioSelector.dispatchEvent(new Event('change'));
    }
});

// ---------------------------------------------------------------------------
// Render loop
// ---------------------------------------------------------------------------

loadScenario();

let lastFrameTime = performance.now();
let frameInterval = navigator.connection && navigator.connection.saveData ? 1000 / 30 : 0;

if (typeof navigator.getBattery === 'function') {
    navigator.getBattery().then(battery => {
        const updateBatteryFrameLimit = () => {
            frameInterval = battery.level <= 0.2 && !battery.charging
                ? 1000 / 30
                : (navigator.connection && navigator.connection.saveData ? 1000 / 30 : 0);
        };
        updateBatteryFrameLimit();
        battery.addEventListener('levelchange', updateBatteryFrameLimit);
        battery.addEventListener('chargingchange', updateBatteryFrameLimit);
    }, error => {
        console.debug('Battery status is unavailable:', error);
    });
}

if (import.meta.env.DEV) {
    window.__AIRSPACE_PERFORMANCE__ = () => renderer.getInfo();
}

function animate() {
    requestAnimationFrame(animate);
    if (document.hidden) return;
    const now = performance.now();
    if (frameInterval && now - lastFrameTime < frameInterval) return;
    // Clamp huge deltas (e.g. after tab switch) so nothing teleports.
    const delta = Math.min((now - lastFrameTime) / 1000, 0.1);
    lastFrameTime = now;

    if (scene.userData.update) scene.userData.update(delta);

    if (cameraTween.active) {
        cameraTween.t = Math.min(1, cameraTween.t + delta / cameraTween.duration);
        const t = cameraTween.t;
        const eased = t < 0.5
            ? 4 * t * t * t
            : 1 - Math.pow(-2 * t + 2, 3) / 2; // ease-in-out cubic
        camera.position.lerpVectors(cameraTween.from, cameraTween.to, eased);
        controls.target.lerpVectors(cameraTween.targetFrom, cameraTween.targetTo, eased);
        if (t >= 1) {
            cameraTween.active = false;
            controls.enabled = true;
        }
    }

    if (activeDataGroup && activeDataGroup.userData.update) {
        activeDataGroup.userData.update(delta);
    }

    routeInspector.update(delta);
    flightHud.update();
    controls.update();
    renderer.render(delta);
}

animate();
document.addEventListener('visibilitychange', () => {
    lastFrameTime = performance.now();
});

window.addEventListener('resize', () => {
    const width = window.innerWidth;
    const height = window.innerHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
});