import * as THREE from 'three';
import { createScene } from './core/scene.js';
import { createCamera } from './core/camera.js';
import { createRenderer } from './core/renderer.js';
import { createLights } from './core/lights.js';
import { createControls } from './core/controls.js';
import { loadModel } from './loaders/modelLoader.js';
import { createPlaneTemplate } from './objects/plane.js';
import { createMapMesh } from './objects/mapMesh.js';
import {
    alignAirportsToMap,
    createSceneDataGroup,
    disposeSceneDataGroup,
    renderMeta,
    renderMetrics,
} from './sceneData.js';
import { fetchSceneData } from './services/routeService.js';

const container = document.getElementById('app');

const scene = createScene();
const camera = createCamera();
const renderer = createRenderer(container);
const controls = createControls(camera, renderer.domElement);
const cameraOffset = new THREE.Vector3(0, 300, 400);
createLights(scene);

const scenarioSelector = document.getElementById('scenario-selector');
const status = document.getElementById('data-status');
const query = new URLSearchParams(window.location.search);
const initialScenario = query.get('scenario') || 'heavy-storms';
const scenarios = new Set(['random-storms', 'heavy-storms', 'clear-airspace']);
scenarioSelector.value = scenarios.has(initialScenario) ? initialScenario : 'heavy-storms';

let activeDataGroup;
let mapMesh;
let requestId = 0;
const mapPromise = loadModel('/models/romania.glb');
const planeTemplatePromise = createPlaneTemplate();

async function loadScenario() {
    const currentRequestId = ++requestId;
    const scenario = scenarioSelector.value;
    status.textContent = `Loading ${scenario}...`;

    try {
        const [payload, mapModel, planeTemplate] = await Promise.all([
            fetchSceneData(scenario),
            mapPromise,
            planeTemplatePromise,
        ]);
        if (currentRequestId !== requestId) return;

        if (!mapMesh) {
            mapMesh = createMapMesh(mapModel, payload.grid, payload.meta?.map_bounds);
            scene.add(mapMesh);
        }

        const nextGroup = createSceneDataGroup(payload, planeTemplate);
        if (activeDataGroup) {
            scene.remove(activeDataGroup);
            disposeSceneDataGroup(activeDataGroup);
        }
        activeDataGroup = nextGroup;
        scene.add(activeDataGroup);
        alignAirportsToMap(activeDataGroup, mapMesh);
        renderMetrics(payload.routes?.metrics || {});
        renderMeta({ ...payload.meta, event_count: payload.events?.length || 0 });

        const bounds = payload.meta?.map_bounds;
        if (bounds) {
            const optimizedRoute = payload.routes?.optimized || [];
            const routeAltitude = optimizedRoute.length ?
                optimizedRoute.reduce((total, waypoint) => total + waypoint.y, 0) / optimizedRoute.length :
                0;
            controls.target.set(
                (bounds.min_x + bounds.max_x) / 2,
                routeAltitude,
                (bounds.min_z + bounds.max_z) / 2,
            );
            camera.position.copy(controls.target).add(cameraOffset);
            camera.lookAt(controls.target);
            controls.update();
        }
    } catch (error) {
        console.error(`Failed to load ${scenario} scenario:`, error);
        if (currentRequestId === requestId) {
            status.textContent = `Could not load ${scenario}: ${error.message}`;
        }
    }
}

scenarioSelector.addEventListener('change', () => {
    const nextQuery = new URLSearchParams(window.location.search);
    nextQuery.set('scenario', scenarioSelector.value);
    window.history.replaceState(null, '', `${window.location.pathname}?${nextQuery}`);
    loadScenario();
});

loadScenario();

const clock = new THREE.Clock();

function animate() {
    requestAnimationFrame(animate);
    const delta = clock.getDelta();
    activeDataGroup?.userData.update?.(delta);
    controls.update();
    renderer.render(scene, camera);
}

animate();

window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});