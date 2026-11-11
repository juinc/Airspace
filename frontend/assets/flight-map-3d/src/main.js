import * as THREE from 'three';
import { createScene } from './core/scene.js';
import { createCamera } from './core/camera.js';
import { createRenderer } from './core/renderer.js';
import { createLights } from './core/lights.js';
import { createControls } from './core/controls.js';
import { loadModel } from './loaders/modelLoader.js';
import { createPlaneTemplate } from './objects/plane.js';
import { createMapMesh, createTerrainHeightSampler } from './objects/mapMesh.js';
import { loadWeatherMeshKit } from './utils/cloudFactory.js';
import { createRouteInspector, sceneToGeo } from './utils/routeInspector.js';
import { applyExecutiveEnvironment } from './utils/executiveEnvironment.js';
import { createBridge } from './bridge.js';
import {
    alignAirportsToMap,
    createSceneDataGroup,
    disposeSceneDataGroup,
    extractPressureLevels,
} from './sceneData.js';
import { checkBackendHealth, fetchSceneData, replanWeatherScene } from './services/routeService.js';

// ---------------------------------------------------------------------------
// Scenario registry — must match backend GET /test-scenarios/{id}
// ---------------------------------------------------------------------------

const SCENARIOS = [
    'crossroads-storm',
    'converge-bucharest',
    'carpathian-siege',
    'storm-wall',
    'over-the-top',
    'low-corridor',
    'slalom',
    'fuel-critical',
    'in-flight-replan',
    'real-meteo',
];

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

// ---------------------------------------------------------------------------
// AGGRESSIVE: device tier detection. Weak phones get 30 FPS cap, 120 cloud
// cells, no glow tubes, no altitude label sprites. Everything still renders.
// ---------------------------------------------------------------------------

const isMobileDevice = window.matchMedia('(max-width: 760px), (pointer: coarse)').matches;
const deviceMemoryGb = navigator.deviceMemory ?? 4;   // Chrome/Android; Safari → default
const cpuCores = navigator.hardwareConcurrency ?? 4;
const isLowEnd = isMobileDevice && (deviceMemoryGb <= 2 || cpuCores <= 4);
const QUALITY = isLowEnd ? 'low' : (isMobileDevice ? 'mid' : 'high');

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

const container = document.getElementById('app');
const modelAssetUrl = file => `${import.meta.env.BASE_URL}models/${file}`;

const bridge = createBridge();

const scene = createScene();
const camera = createCamera();
const renderer = createRenderer(container, scene, camera);
const controls = createControls(camera, renderer.domElement);
createLights(scene);
applyExecutiveEnvironment(scene);

// Camera sits on the SOUTH side of the corridor, looking north.
const cameraOffset = new THREE.Vector3(0, 520, -720);

const cameraTween = {
    active: false,
    from: new THREE.Vector3(),
    to: new THREE.Vector3(),
    targetFrom: new THREE.Vector3(),
    targetTo: new THREE.Vector3(),
    t: 0,
    duration: 1.8,
};

let cameraMode = 'free'; // 'free' | 'follow'
const followDelta = new THREE.Vector3();

function startCameraTween(targetPosition, targetLook) {
    cameraTween.from.copy(camera.position);
    cameraTween.to.copy(targetPosition);
    cameraTween.targetFrom.copy(controls.target);
    cameraTween.targetTo.copy(targetLook);
    cameraTween.t = 0;
    cameraTween.active = true;
    controls.enabled = false;
}

function cancelCameraTween() {
    if (!cameraTween.active) return;
    cameraTween.active = false;
    controls.enabled = true;
}

renderer.domElement.addEventListener('pointerdown', () => {
    cancelCameraTween();
    cameraMode = 'free';
});
renderer.domElement.addEventListener('wheel', cancelCameraTween, { passive: true });

// ---------------------------------------------------------------------------
// Scenario state
// ---------------------------------------------------------------------------

const query = new URLSearchParams(window.location.search);
let currentScenario = SCENARIOS.includes(query.get('scenario')) ? query.get('scenario') : 'crossroads-storm';

let activeDataGroup;
let activePayload;
let activePlaneTemplate;
let activeWeatherMeshKit;
let weatherUpdateTimer;
let weatherUpdateNumber = 0;
let mapMesh;
let terrainModel;
let groundSampler = null;
let requestId = 0;
let activeScenarioController;

// Which aircraft drives the HUD (chips in Flutter + clicking planes).
let selectedFlightIndex = 0;

// Plane template is small (211 KB mobile) — worth waiting for so the scene
// is built exactly ONCE. Terrain is big and loads in parallel WITHOUT
// blocking the first paint; airports get aligned in place when it lands.
const mapPromise = loadModel(modelAssetUrl(isMobileDevice ? 'romania-mobile.glb' : 'romania.glb'));
const planeTemplatePromise = createPlaneTemplate(
    isMobileDevice ? modelAssetUrl('plane-mobile.glb') : undefined,
);
const weatherKitPromise = loadWeatherMeshKit();

const withTimeout = (promise, ms, fallback) => Promise.race([
    promise.catch(() => fallback),
    new Promise(resolve => setTimeout(() => resolve(fallback), ms)),
]);

function setStatus(text) {
    const bootStatus = document.getElementById('boot-status');
    if (bootStatus) bootStatus.textContent = text;
    bridge.emit('airspace:status', { text });
}

function getPlaneState() {
    const states = activeDataGroup && activeDataGroup.userData.planeStates;
    if (!states || !states.length) return null;
    return states[Math.min(selectedFlightIndex, states.length - 1)]();
}

function getFlightProgress() {
    const state = getPlaneState();
    return state ? state.progress : 0.35;
}

function getFlightIds() {
    return (activeDataGroup && activeDataGroup.userData.flightIds) || [];
}

function selectFlight(index) {
    const count = (activeDataGroup && activeDataGroup.userData.flightCount) || 1;
    selectedFlightIndex = Math.max(0, Math.min(Number.isFinite(index) ? index : 0, count - 1));
    bridge.emit('airspace:flight-selected', {
        index: selectedFlightIndex,
        id: getFlightIds()[selectedFlightIndex] ?? null,
    });
}

weatherKitPromise.then(kit => {
    activeWeatherMeshKit = kit;
    // Kit arrived after the scene was built? Refresh ONLY the weather layer —
    // routes, planes and labels are untouched.
    if (activeDataGroup && activePayload) {
        activeDataGroup.userData.updateWeather(activePayload.grid, kit);
    }
}, error => {
    console.warn('Weather kit unavailable:', error);
});

checkBackendHealth().then(health => {
    if (!health.ok) {
        setStatus(`Backend unavailable (${health.detail}) — retrying scenarios anyway…`);
    }
});

function attachTerrainModel() {
    if (!terrainModel || !activePayload || mapMesh) return;
    try {
        mapMesh = createMapMesh(
            terrainModel,
            activePayload.grid,
            activePayload.meta && activePayload.meta.map_bounds,
        );
    } catch (error) {
        console.warn('Romania map unavailable:', error);
        bridge.emit('airspace:error', { message: `Romania map unavailable: ${error.message}` });
        return;
    }
    scene.add(mapMesh);
    groundSampler = createTerrainHeightSampler(mapMesh, isLowEnd ? 64 : 96);
    if (activeDataGroup) alignAirportsToMap(activeDataGroup, groundSampler);
}

// Terrain and scenario data load independently. Retain the model if it wins
// the race so a fast local GLB load cannot permanently skip the map.
mapPromise.then(model => {
    terrainModel = model;
    attachTerrainModel();
}, error => {
    console.warn('Romania map unavailable:', error);
    bridge.emit('airspace:error', { message: `Romania map unavailable: ${error.message}` });
});

// ---------------------------------------------------------------------------
// Click-to-inspect — the ONLY UI kept inside the WebView.
// ---------------------------------------------------------------------------

const routeInspector = createRouteInspector({
    camera,
    domElement: renderer.domElement,
    getDataGroup: () => activeDataGroup,
    getPayload: () => activePayload,
    getAircraft: () => (activeDataGroup && activeDataGroup.userData.aircraftMeshes) || [],
    onFlightSelected: index => selectFlight(index),
    scene,
    bridge,
});

// ---------------------------------------------------------------------------
// Scenario loading — ONE scene build per payload.
// ---------------------------------------------------------------------------

async function loadScenario(scenario, routeProgress = 0.35) {
    if (!SCENARIOS.includes(scenario)) {
        bridge.emit('airspace:error', { scenario, message: `Unknown scenario: ${scenario}` });
        return;
    }

    const currentRequestId = ++requestId;
    if (activeScenarioController) activeScenarioController.abort();
    const scenarioController = new AbortController();
    activeScenarioController = scenarioController;
    currentScenario = scenario;
    setStatus(`Loading ${scenario}…`);

    try {
        const payload = await (scenario === 'in-flight-replan' && activePayload
            ? replanWeatherScene(activePayload, routeProgress, undefined, scenarioController.signal)
            : fetchSceneData(scenario, routeProgress, scenarioController.signal));
        if (currentRequestId !== requestId) return;

        // Wait at most 2.5 s for the SMALL plane model so the group is built
        // exactly once. On timeout we build without the aircraft and it
        // appears on the next scenario switch (browser cache makes that rare).
        activePlaneTemplate = activePlaneTemplate
            || await withTimeout(planeTemplatePromise, 2500, null);

        // New scenario -> selection resets to the lead aircraft.
        selectedFlightIndex = 0;
        applyScenePayload(payload, routeProgress, !!activeWeatherMeshKit);

        // First paint is live NOW — Flutter hides its loader immediately;
        // terrain continues loading invisibly in the background.
        document.body.classList.add('scene-ready');
        emitScenarioLoaded(scenario, payload);
        frameCameraToPayload(payload, 'corridor');
        scheduleWeatherUpdate();
    } catch (error) {
        if (currentRequestId === requestId) {
            console.error(`Failed to load ${scenario} scenario:`, error);
            setStatus(`Could not load ${scenario}: ${error.message}`);
            bridge.emit('airspace:error', { scenario, message: error.message });
        }
    } finally {
        if (activeScenarioController === scenarioController) activeScenarioController = undefined;
        document.body.classList.add('scene-ready');
    }
}

function applyScenePayload(payload, initialProgress = 0, includeWeather = true) {
    routeInspector.clear();

    const nextGroup = createSceneDataGroup(
        payload,
        activePlaneTemplate,
        initialProgress,
        includeWeather ? activeWeatherMeshKit : null,
        groundSampler,
        includeWeather,
        QUALITY,
    );
    if (activeDataGroup) {
        scene.remove(activeDataGroup);
        disposeSceneDataGroup(activeDataGroup);
    }
    activeDataGroup = nextGroup;
    activePayload = payload;
    attachTerrainModel();
    scene.add(activeDataGroup);
    if (groundSampler) alignAirportsToMap(activeDataGroup, groundSampler);
}

function emitScenarioLoaded(scenario, payload) {
    const meta = payload.meta || {};
    const metrics = (payload.routes && payload.routes.metrics) || {};
    bridge.emit('airspace:scenario-loaded', {
        scenario,
        title: meta.scenario_title || SCENARIO_TITLES[scenario] || scenario,
        meta: {
            source: meta.source,
            fetched_at: meta.fetched_at,
            trajectory_status: meta.trajectory_status,
            event_count: (payload.events && payload.events.length) || 0,
            vertical_exaggeration: meta.vertical_exaggeration ?? 4,
        },
        metrics,
        routing_assumptions: meta.routing_assumptions || null,
        legend: extractPressureLevels(payload.grid || []),
        flights: (payload.flights || []).map(flight => ({
            id: flight.id,
            origin: flight.origin,
            destination: flight.destination,
        })),
        flight_count: (activeDataGroup && activeDataGroup.userData.flightCount) || 1,
        weather_update: payload.weather_update || null,
    });
}

// ---------------------------------------------------------------------------
// Live flight state — computed once (null-safe, rounded, metric), 10 Hz.
// ---------------------------------------------------------------------------

function computeFlightState(payload, state) {
    if (!payload || !state) return null;

    const metrics = (payload.routes && payload.routes.metrics
        && payload.routes.metrics.optimized) || {};
    const waypoints = (payload.routes && payload.routes.optimized) || [];
    const profile = (payload.meta && payload.meta.routing_assumptions
        && payload.meta.routing_assumptions.aircraft_profile) || {};
    const geo = sceneToGeo(state.position);

    const climbRate = profile.climb_rate_m_per_min ?? 1189;
    const descentRate = profile.descent_rate_m_per_min ?? 600;
    const cruiseSpeed = profile.cruise_speed_kmh ?? 770.4;
    let verticalSpeed = 0;
    let groundSpeed = cruiseSpeed;
    if (state.phase === 'TAKEOFF' || state.phase === 'CLIMB') {
        verticalSpeed = climbRate / 60;
    } else if (state.phase === 'DESCENT') {
        verticalSpeed = -descentRate / 60;
    } else if (state.phase === 'LANDED') {
        groundSpeed = 0;
    }

    let exposure = null;
    let bestDistance = Infinity;
    for (const waypoint of waypoints) {
        const d = (waypoint.x - state.position.x) ** 2 + (waypoint.z - state.position.z) ** 2;
        if (d < bestDistance) {
            bestDistance = d;
            exposure = waypoint.exposure_score;
        }
    }

    const totalMin = metrics.time_min;
    const initialFuel = metrics.initial_fuel_kg;
    const burnTotal = metrics.fuel_estimated_kg;
    let fuelRemaining = null;
    let fuelPercent = null;
    let burnRate = null;
    if (initialFuel != null && burnTotal != null && totalMin > 0) {
        const remaining = Math.max(0, initialFuel - burnTotal * state.progress);
        fuelRemaining = Math.round(remaining);
        fuelPercent = Math.max(0, Math.min(100, Math.round((remaining / initialFuel) * 100)));
        burnRate = Math.round(burnTotal / (totalMin / 60));
    }

    return {
        flight_index: selectedFlightIndex,
        flight_id: getFlightIds()[selectedFlightIndex] ?? null,
        progress: Number(state.progress.toFixed(3)),
        phase: state.phase,
        lat: Number(geo.lat.toFixed(4)),
        lon: Number(geo.lon.toFixed(4)),
        altitude_km: Number(state.altitude_km.toFixed(2)),
        vertical_speed_m_per_s: Number(verticalSpeed.toFixed(1)),
        ground_speed_kmh: Math.round(groundSpeed),
        exposure_score: exposure,
        fuel_remaining_kg: fuelRemaining,
        fuel_percent: fuelPercent,
        burn_rate_kg_per_h: burnRate,
        eta_min: totalMin ? Number(Math.max(0, totalMin * (1 - state.progress)).toFixed(1)) : null,
        distance_remaining_km: metrics.distance_km != null
            ? Number((metrics.distance_km * (1 - state.progress)).toFixed(1))
            : null,
    };
}

// ---------------------------------------------------------------------------
// Camera presets
// ---------------------------------------------------------------------------

const CAMERA_PRESETS = {
    corridor: new THREE.Vector3(0, 520, -720),
    overview: new THREE.Vector3(0, 980, -1250),
    top: new THREE.Vector3(0, 1500, -10),
};

function frameCameraToPayload(payload, preset = 'corridor') {
    const bounds = payload.meta && payload.meta.map_bounds;
    if (!bounds) return;
    const optimizedRoute = (payload.routes && payload.routes.optimized) || [];
    const routeAltitude = optimizedRoute.length
        ? optimizedRoute.reduce((total, waypoint) => total + waypoint.y, 0) / optimizedRoute.length
        : 0;
    const lookAt = new THREE.Vector3(
        (bounds.min_x + bounds.max_x) / 2,
        routeAltitude,
        (bounds.min_z + bounds.max_z) / 2,
    );
    const offset = CAMERA_PRESETS[preset] || CAMERA_PRESETS.corridor;
    startCameraTween(lookAt.clone().add(offset), lookAt);
}

function setCameraPreset(preset, position, target) {
    if (Array.isArray(position) && Array.isArray(target)) {
        cameraMode = 'free';
        startCameraTween(new THREE.Vector3(...position), new THREE.Vector3(...target));
        return;
    }
    cameraMode = preset === 'follow' ? 'follow' : 'free';
    if (preset === 'follow') return;
    if (activePayload) frameCameraToPayload(activePayload, preset);
}

// ---------------------------------------------------------------------------
// Live weather updates (in-flight-replan scenario)
// ---------------------------------------------------------------------------

function scheduleWeatherUpdate() {
    window.clearTimeout(weatherUpdateTimer);
    if (currentScenario !== 'in-flight-replan' || !activePayload) return;
    const delay = 7000 + Math.random() * 8000;
    weatherUpdateTimer = window.setTimeout(runWeatherUpdate, delay);
}

async function runWeatherUpdate() {
    const previousPayload = activePayload;
    if (!previousPayload || currentScenario !== 'in-flight-replan') return;

    const progress = getFlightProgress();
    const weatherSeed = Math.floor(Math.random() * 2147483647);
    const updateNumber = ++weatherUpdateNumber;
    setStatus(`Checking weather change ${updateNumber}…`);

    try {
        const nextPayload = await replanWeatherScene(previousPayload, progress, weatherSeed);
        if (activePayload !== previousPayload || currentScenario !== 'in-flight-replan') return;

        nextPayload.meta.trajectory_status = nextPayload.weather_update.replanned
            ? `Weather update ${updateNumber}: ${nextPayload.meta.trajectory_status}`
            : `Weather update ${updateNumber}: route unchanged below drastic threshold`;
        applyScenePayload(nextPayload, nextPayload.weather_update.replanned ? 0 : progress, !!activeWeatherMeshKit);
        emitScenarioLoaded(currentScenario, nextPayload);
        bridge.emit('airspace:weather-updated', {
            update_number: updateNumber,
            replanned: !!nextPayload.weather_update.replanned,
            trajectory_status: nextPayload.meta.trajectory_status,
        });
    } catch (error) {
        console.error('Weather update failed:', error);
        setStatus(`Weather update failed: ${error.message}`);
        bridge.emit('airspace:error', { message: `Weather update failed: ${error.message}` });
    } finally {
        scheduleWeatherUpdate();
    }
}

// ---------------------------------------------------------------------------
// Bridge commands (Flutter -> Three.js) — see BRIDGE_PROTOCOL.md
// ---------------------------------------------------------------------------

bridge.onCommand('airspace:loadScenario', ({ scenario, routeProgress }) =>
    loadScenario(scenario, Number.isFinite(routeProgress) ? routeProgress : getFlightProgress()));

bridge.onCommand('airspace:setCamera', ({ preset, position, target }) =>
    setCameraPreset(preset, position, target));

bridge.onCommand('airspace:toggleLayer', ({ layer, visible }) => {
    if (layer === 'terrain') {
        if (mapMesh) mapMesh.visible = !!visible;
        return;
    }
    if (activeDataGroup && activeDataGroup.userData.setLayerVisible) {
        activeDataGroup.userData.setLayerVisible(layer, !!visible);
    }
});

bridge.onCommand('airspace:replanWeather', () => {
    window.clearTimeout(weatherUpdateTimer);
    return runWeatherUpdate();
});

bridge.onCommand('airspace:clearSelection', () => routeInspector.clear());

bridge.onCommand('airspace:selectFlight', ({ index }) => selectFlight(Number(index) || 0));

bridge.emit('airspace:ready', {
    scenarios: SCENARIOS.map(id => ({ id, title: SCENARIO_TITLES[id] || id })),
    mobile: isMobileDevice,
    quality: QUALITY,
});

// ---------------------------------------------------------------------------
// Render loop — 30 FPS hard cap on low-end devices (halves GPU + JS cost;
// a flight-sim visualization is perfectly smooth at 30).
// ---------------------------------------------------------------------------

loadScenario(currentScenario);

let lastFrameTime = performance.now();
let lastStateEmit = 0;
let frameInterval = isLowEnd ? 1000 / 30 : 0;
if (!isLowEnd && navigator.connection && navigator.connection.saveData) {
    frameInterval = 1000 / 30;
}

if (!isLowEnd && typeof navigator.getBattery === 'function') {
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

if (import.meta.env.DEV || new URLSearchParams(window.location.search).has('benchmark')) {
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
    } else if (cameraMode === 'follow') {
        const state = getPlaneState();
        if (state) {
            followDelta.copy(state.position).sub(controls.target)
                .multiplyScalar(Math.min(1, delta * 2.5));
            controls.target.add(followDelta);
            camera.position.add(followDelta);
        }
    }

    if (activeDataGroup && activeDataGroup.userData.update) {
        activeDataGroup.userData.update(delta);
    }

    routeInspector.update(delta);
    controls.update();
    renderer.render();

    // Flight state to Flutter at 10 Hz — never per-frame.
    if (now - lastStateEmit >= 100) {
        lastStateEmit = now;
        const data = computeFlightState(activePayload, getPlaneState());
        if (data) bridge.emit('airspace:flight-state', data);
    }
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