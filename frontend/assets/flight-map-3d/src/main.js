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
import { createRouteInspector, sceneToGeo } from './utils/routeInspector.js';
import { applyExecutiveEnvironment } from './utils/executiveEnvironment.js';
import { createAirspaceBridge } from './utils/airspaceBridge.js';
import { mountStandaloneUi } from './utils/standaloneUi.js';

import {
    alignAirportsToMap,
    createSceneDataGroup,
    disposeSceneDataGroup,
} from './sceneData.js';
import {
    checkBackendHealth,
    fetchSceneData,
    replanWeatherScene,
    setApiBaseUrl,
} from './services/routeService.js';

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

const container = document.getElementById('app');
const isMobileDevice = window.matchMedia('(max-width: 760px), (pointer: coarse)').matches;
const modelAssetUrl = file => `${import.meta.env.BASE_URL}models/${file}`;

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

const query = new URLSearchParams(window.location.search);

const SCENARIOS = [
    { id: 'crossroads-storm', title: 'Storm crossroads — 3 aircraft' },
    { id: 'converge-bucharest', title: 'Converge on Bucharest — 4 aircraft' },
    { id: 'carpathian-siege', title: 'Carpathian siege — triangle flights' },
    { id: 'storm-wall', title: 'Storm wall' },
    { id: 'over-the-top', title: 'Over the top' },
    { id: 'low-corridor', title: 'Low corridor' },
    { id: 'slalom', title: 'Slalom' },
    { id: 'fuel-critical', title: 'Fuel critical' },
    { id: 'in-flight-replan', title: 'In-flight replan' },
    { id: 'real-meteo', title: 'Real meteo (AIFS)' },
    { id: 'random-storms', title: 'Random storms' },
    { id: 'heavy-storms', title: 'Heavy storms' },
    { id: 'clear-airspace', title: 'Clear airspace' },
    { id: 'layered-random', title: 'Layered weather' },
];
const scenarioIds = new Set(SCENARIOS.map(scenario => scenario.id));
const initialScenario = query.get('scenario') || 'crossroads-storm';
let activeScenario = scenarioIds.has(initialScenario) ? initialScenario : 'crossroads-storm';

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
let bridge;
let lastTelemetryAt = -Infinity;
let pendingCameraPreset;

const mapPromise = loadModel(modelAssetUrl(isMobileDevice ? 'romania-mobile.glb' : 'romania.glb'));
const planeTemplatePromise = createPlaneTemplate(
    isMobileDevice ? modelAssetUrl('plane-mobile.glb') : undefined,
);
const weatherKitPromise = loadWeatherMeshKit();

function setStatus(text) {
    bridge?.emit('status', { message: text, scenario: activeScenario });
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
    onSelection: payload => bridge?.emit('coordinateClick', payload),
    onClear: () => bridge?.emit('coordinateCleared'),
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

async function loadScenario(scenario = activeScenario, routeProgress) {
    if (!scenarioIds.has(scenario)) {
        const message = `Unknown scenario: ${scenario}`;
        bridge?.emit('error', { message, scenario });
        return;
    }

    const currentRequestId = ++requestId;
    if (activeScenarioController) activeScenarioController.abort();
    const scenarioController = new AbortController();
    activeScenarioController = scenarioController;
    activeScenario = scenario;
    const currentProgress = Number.isFinite(routeProgress)
        ? THREE.MathUtils.clamp(routeProgress, 0, 1)
        : (activeDataGroup?.userData.getFlightProgress?.() ?? 0.35);
    setStatus(`Loading ${scenario}…`);
    const queryParameters = new URLSearchParams(window.location.search);
    queryParameters.set('scenario', scenario);
    window.history.replaceState(null, '', `${window.location.pathname}?${queryParameters}`);

    try {
        const payload = await (scenario === 'in-flight-replan' && activePayload
            ? replanWeatherScene(activePayload, currentProgress, undefined, scenarioController.signal)
            : fetchSceneData(scenario, currentProgress, scenarioController.signal));
        if (currentRequestId !== requestId) return;

        const initialProgress = scenario === 'in-flight-replan' && activePayload
            ? 0
            : currentProgress;
        applyScenePayload(payload, initialProgress, false);
        scheduleWeatherRender(payload, currentRequestId);
        bridge?.emit('scenarioLoaded', createScenarioSummary(payload, scenario));
        setStatus('Scenario data loaded — preparing terrain and aircraft…');

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
            applyCameraPreset(pendingCameraPreset || 'overview', lookAt);
            pendingCameraPreset = undefined;
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
                bridge?.emit('error', { message: 'Romania terrain model could not be loaded.', scenario });
            }
        }

        if (mapMesh && !groundSampler) groundSampler = createGroundSampler(mapMesh);

        activePlaneTemplate = planeResult.status === 'fulfilled' ? planeResult.value : null;
        if (planeResult.status === 'rejected') console.warn('Aircraft model unavailable:', planeResult.reason);
        if (mapMesh || activePlaneTemplate) {
            applyScenePayload(payload, initialProgress, false);
            scheduleWeatherRender(payload, currentRequestId);
        }
        setStatus('Scene ready.');

        scheduleWeatherUpdate();
    } catch (error) {
        if (currentRequestId === requestId) {
            console.error(`Failed to load ${scenario} scenario:`, error);
            const message = `Could not load ${scenario}: ${error.message}`;
            setStatus(message);
            bridge?.emit('error', { message, scenario });
        }
    } finally {
        if (activeScenarioController === scenarioController) activeScenarioController = undefined;
    }
}

function applyScenePayload(payload, initialProgress = 0, includeWeather = true) {
    // Clear a selection tied to geometry from the previous scenario.
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
}

function createScenarioSummary(payload, scenario) {
    const routes = payload.routes || {};
    const defaultAirports = payload.airports || [];
    const rawFlights = Array.isArray(payload.flights) && payload.flights.length
        ? payload.flights
        : [{ id: 'F1', ...routes }];
    const flights = rawFlights.map((flight, index) => ({
        id: flight.id || `F${index + 1}`,
        origin: flight.origin || defaultAirports[0]?.name || null,
        destination: flight.destination || defaultAirports[defaultAirports.length - 1]?.name || null,
        metrics: flight.metrics || (index === 0 ? routes.metrics : null),
    }));
    const pressureLevels = new Map();
    for (const point of payload.grid || []) {
        for (const [pressure, level] of Object.entries(point.levels || {})) {
            if (!Number.isFinite(level?.altitude_km)) continue;
            const numericPressure = Number(pressure);
            if (!Number.isFinite(numericPressure)) continue;
            if (!pressureLevels.has(numericPressure)) pressureLevels.set(numericPressure, []);
            pressureLevels.get(numericPressure).push(level.altitude_km);
        }
    }

    return {
        scenario,
        meta: {
            source: payload.meta?.source || 'unknown',
            title: payload.meta?.scenario_title || SCENARIOS.find(item => item.id === scenario)?.title || scenario,
            fetchedAt: payload.meta?.fetched_at || null,
            trajectoryStatus: payload.meta?.trajectory_status || null,
            aircraftProfile: payload.meta?.routing_assumptions?.aircraft_profile || null,
        },
        metrics: routes.metrics || null,
        flights,
        pressureLevels: [...pressureLevels.entries()]
            .map(([pressure, altitudes]) => ({
                pressure,
                altitudeKm: medianValue(altitudes),
            }))
            .sort((left, right) => left.altitudeKm - right.altitudeKm),
        eventCount: (payload.events || []).reduce(
            (total, event) => total + (Number.isFinite(event.cell_count) ? event.cell_count : 1),
            0,
        ),
    };
}

function medianValue(values) {
    const sorted = values.slice().sort((left, right) => left - right);
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2
        ? sorted[middle]
        : (sorted[middle - 1] + sorted[middle]) / 2;
}

function applyCameraPreset(preset, lookAt) {
    const bounds = activePayload?.meta?.map_bounds;
    const target = lookAt || (bounds
        ? new THREE.Vector3(
            (bounds.min_x + bounds.max_x) / 2,
            0,
            (bounds.min_z + bounds.max_z) / 2,
        )
        : controls.target.clone());
    const offset = preset === 'topDown'
        ? new THREE.Vector3(0, 1150, -0.01)
        : cameraOffset;
    startCameraTween(target.clone().add(offset), target);
}

function setLayerVisibility(layer, visible) {
    const validLayers = new Set(['weather', 'routes', 'airports', 'altitude']);
    if (!validLayers.has(layer)) {
        bridge?.emit('error', { message: `Unknown scene layer: ${layer}` });
        return;
    }
    if (!activeDataGroup) return;
    activeDataGroup.traverse(object => {
        if (object.userData.layer === layer) object.visible = visible;
    });
}

function createTelemetry(state, route, index) {
    if (!state?.position || !activePayload) return null;
    const optimized = route?.optimized || [];
    const metrics = route?.metrics?.optimized || {};
    const profile = activePayload.meta?.routing_assumptions?.aircraft_profile || {};
    const position = state.position;
    let nearestWaypoint = null;
    let nearestDistance = Infinity;
    for (const waypoint of optimized) {
        if (!Number.isFinite(waypoint.x) || !Number.isFinite(waypoint.z)) continue;
        const distance = (waypoint.x - position.x) ** 2 + (waypoint.z - position.z) ** 2;
        if (distance < nearestDistance) {
            nearestDistance = distance;
            nearestWaypoint = waypoint;
        }
    }

    const progress = THREE.MathUtils.clamp(state.progress, 0, 1);
    const cruiseSpeed = profile.cruise_speed_kmh;
    const climbRate = profile.climb_rate_m_per_min;
    const descentRate = profile.descent_rate_m_per_min;
    const totalTime = metrics.time_min;
    const totalFuel = metrics.fuel_estimated_kg;
    const initialFuel = metrics.initial_fuel_kg;
    let fuelRemaining = null;
    let eta = null;
    if (Number.isFinite(totalTime) && totalTime > 0) {
        const cumulativeTime = nearestWaypoint?.cumulative_time_min;
        const timeElapsed = Number.isFinite(cumulativeTime) ? cumulativeTime : totalTime * progress;
        eta = Math.max(0, totalTime - timeElapsed);
        if (Number.isFinite(initialFuel) && Number.isFinite(totalFuel)) {
            fuelRemaining = Math.max(0, initialFuel - (totalFuel / totalTime) * timeElapsed);
        }
    }
    const geo = sceneToGeo(position);
    let verticalSpeed = null;
    if (state.phase === 'CLIMB' || state.phase === 'TAKEOFF') {
        verticalSpeed = Number.isFinite(climbRate) ? climbRate / 60 : null;
    } else if (state.phase === 'DESCENT') {
        verticalSpeed = Number.isFinite(descentRate) ? -descentRate / 60 : null;
    } else if (state.phase === 'CRUISE') {
        verticalSpeed = 0;
    }
    const groundSpeed = state.phase === 'LANDED'
        ? 0
        : Number.isFinite(cruiseSpeed) ? cruiseSpeed : null;

    return {
        flightId: route?.id || `F${index + 1}`,
        phase: state.phase,
        lat: Number(geo.lat.toFixed(5)),
        lon: Number(geo.lon.toFixed(5)),
        altitudeKm: Number(state.altitude_km.toFixed(2)),
        groundSpeedKmH: Number.isFinite(groundSpeed) ? Number(groundSpeed.toFixed(0)) : null,
        verticalSpeedMps: Number.isFinite(verticalSpeed) ? Number(verticalSpeed.toFixed(1)) : null,
        progress: Number(progress.toFixed(4)),
        exposureScore: nearestWaypoint?.exposure_score ?? null,
        fuelRemainingKg: fuelRemaining == null ? null : Math.round(fuelRemaining),
        etaMin: eta == null ? null : Number(eta.toFixed(1)),
        distanceRemainingKm: Number.isFinite(metrics.distance_km)
            ? Number((metrics.distance_km * (1 - progress)).toFixed(1))
            : null,
    };
}

function updateTelemetry(now) {
    if (!bridge || !activeDataGroup || now - lastTelemetryAt < 500) return;
    lastTelemetryAt = now;
    const planeStates = activeDataGroup.userData.planeStates || [];
    if (!planeStates.length) return;
    const flights = Array.isArray(activePayload?.flights) && activePayload.flights.length
        ? activePayload.flights
        : [{ id: 'F1', ...(activePayload?.routes || {}) }];
    for (let index = 0; index < planeStates.length; index++) {
        const telemetry = createTelemetry(planeStates[index](), flights[index], index);
        if (telemetry) bridge.emit('telemetry', telemetry);
    }
}

// ---------------------------------------------------------------------------
// Live weather updates (in-flight-replan scenario)
// ---------------------------------------------------------------------------

function scheduleWeatherUpdate() {
    window.clearTimeout(weatherUpdateTimer);
    if (activeScenario !== 'in-flight-replan' || !activePayload) return;

    const delay = 7000 + Math.random() * 8000;
    weatherUpdateTimer = window.setTimeout(runWeatherUpdate, delay);
}

async function runWeatherUpdate() {
    const previousPayload = activePayload;
    if (!previousPayload || activeScenario !== 'in-flight-replan') return;

    const progress = activeDataGroup && activeDataGroup.userData.getFlightProgress
        ? activeDataGroup.userData.getFlightProgress()
        : 0;
    const weatherSeed = Math.floor(Math.random() * 2147483647);
    const updateNumber = ++weatherUpdateNumber;
    setStatus(`Checking weather change ${updateNumber}…`);

    try {
        const nextPayload = await replanWeatherScene(previousPayload, progress, weatherSeed);
        if (activePayload !== previousPayload || activeScenario !== 'in-flight-replan') return;

        nextPayload.meta.trajectory_status = nextPayload.weather_update.replanned
            ? `Weather update ${updateNumber}: ${nextPayload.meta.trajectory_status}`
            : `Weather update ${updateNumber}: route unchanged below drastic threshold`;
        applyScenePayload(nextPayload, nextPayload.weather_update.replanned ? 0 : progress, false);
        scheduleWeatherRender(nextPayload, requestId);
        bridge?.emit('scenarioLoaded', createScenarioSummary(nextPayload, activeScenario));
    } catch (error) {
        console.error('Weather update failed:', error);
        setStatus(`Weather update failed: ${error.message}`);
    } finally {
        scheduleWeatherUpdate();
    }
}

// ---------------------------------------------------------------------------
// Flutter bridge
// ---------------------------------------------------------------------------

function handleBridgeCommand(command) {
    if (command.action === 'loadScenario' && typeof command.scenario === 'string') {
        window.clearTimeout(weatherUpdateTimer);
        loadScenario(command.scenario, command.routeProgress);
        return;
    }
    if (command.action === 'setCamera' && ['overview', 'topDown'].includes(command.preset)) {
        if (activePayload) applyCameraPreset(command.preset);
        else pendingCameraPreset = command.preset;
        return;
    }
    if (command.action === 'toggleLayer'
        && typeof command.layer === 'string'
        && typeof command.visible === 'boolean') {
        setLayerVisibility(command.layer, command.visible);
        return;
    }
    if (command.action === 'setApiBase' && typeof command.url === 'string') {
        try {
            setApiBaseUrl(command.url);
            checkBackendHealth().then(health => {
                if (health.ok) setStatus('Backend connected.');
                else {
                    const message = `Backend unavailable (${health.detail}).`;
                    setStatus(message);
                    bridge?.emit('error', { message });
                }
            });
        } catch (error) {
            bridge?.emit('error', { message: error.message });
        }
    }
}

// ---------------------------------------------------------------------------
// Render loop
// ---------------------------------------------------------------------------

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
    updateTelemetry(now);
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

bridge = createAirspaceBridge(handleBridgeCommand);
if (!bridge.isEmbedded()) {
    mountStandaloneUi({
        scenarios: SCENARIOS,
        initialScenario: activeScenario,
        sendCommand: command => window.AirspaceThree.receiveMessage({
            version: 1,
            type: 'command',
            ...command,
        }),
    });
}
bridge.emit('ready', { scenarios: SCENARIOS, initialScenario: activeScenario });
if (!bridge.isEmbedded()) loadScenario(activeScenario);
