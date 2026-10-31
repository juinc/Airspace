import * as THREE from 'three';
import { createScene } from './core/scene.js';
import { createCamera } from './core/camera.js';
import { createRenderer } from './core/renderer.js';
import { createLights } from './core/lights.js';
import { createControls } from './core/controls.js';
import { createMapMesh, getMapPlaneY } from './objects/mapMesh.js';
import { loadModel } from './loaders/modelLoader.js';
import {
    alignAirportsToMap,
    createSceneDataGroup,
    disposeSceneDataGroup,
    renderMeta,
    renderMetrics,
} from './sceneData.js';

const container = document.getElementById('app');
const scene = createScene();
const mapPlaneY = getMapPlaneY();
const camera = createCamera(mapPlaneY);
const renderer = createRenderer(container);
const controls = createControls(camera, renderer.domElement, mapPlaneY);

createLights(scene);

let sceneDataGroup = null;
let mapMesh = null;
let currentPayload = null;

function fitCameraToScene() {
    const bounds = new THREE.Box3().setFromObject(scene);
    if (bounds.isEmpty()) return;

    const halfX = Math.max(Math.abs(bounds.min.x), Math.abs(bounds.max.x));
    const halfY = Math.max(Math.abs(bounds.min.y - mapPlaneY), Math.abs(bounds.max.y - mapPlaneY));
    const halfZ = Math.max(Math.abs(bounds.min.z), Math.abs(bounds.max.z));
    const radius = Math.hypot(halfX, halfY, halfZ);
    const aspect = container.clientWidth / Math.max(container.clientHeight, 1);
    const verticalHalfFov = THREE.MathUtils.degToRad(camera.fov) / 2;
    const horizontalHalfFov = Math.atan(Math.tan(verticalHalfFov) * aspect);
    const limitingHalfFov = Math.min(verticalHalfFov, horizontalHalfFov);
    const fitDistance = radius / Math.sin(limitingHalfFov) * 1.15;
    const target = new THREE.Vector3(0, mapPlaneY, 0);
    const viewDirection = new THREE.Vector3(0, 0.58, 0.815).normalize();

    camera.position.copy(target).addScaledVector(viewDirection, fitDistance);
    camera.far = Math.max(5000, fitDistance * 4);
    camera.lookAt(target);
    camera.updateProjectionMatrix();

    controls.target.copy(target);
    controls.minDistance = Math.max(4, fitDistance * 0.025);
    controls.maxDistance = fitDistance * 1.6;
    controls.update();
}

function showError(error) {
    console.error('Failed to load scene data:', error);
    const status = document.getElementById('data-status');
    if (status) status.textContent = `ERROR: ${error.message}`;
}

async function loadSceneData(payload) {
    if (!payload || !Array.isArray(payload.grid)) {
        throw new Error('Backend response is missing its grid data.');
    }

    const nextGroup = createSceneDataGroup(payload);
    if (sceneDataGroup) {
        scene.remove(sceneDataGroup);
        disposeSceneDataGroup(sceneDataGroup);
    }
    sceneDataGroup = nextGroup;
    scene.add(sceneDataGroup);
    currentPayload = payload;

    if (!mapMesh) {
        const model = await loadModel('/models/romania.glb');
        const mapBounds = payload.meta && payload.meta.map_bounds;
        mapMesh = createMapMesh(model, payload.grid, mapBounds);
        scene.add(mapMesh);
    }

    alignAirportsToMap(sceneDataGroup, mapMesh);
    renderMeta(payload.meta || {});
    renderMetrics((payload.routes && payload.routes.metrics) || {});
    fitCameraToScene();
}

async function fetchAndLoad(preference = 'balanced') {
    const status = document.getElementById('data-status');
    if (status) status.textContent = 'Loading forecast scene...';

    try {
        const apiBase =
            import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
        const response = await fetch(new URL('/test-scene-data', apiBase), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ test_mode: false, preference }),
        });
        if (!response.ok) throw new Error(`Backend returned ${response.status}`);
        await loadSceneData(await response.json());
    } catch (error) {
        showError(error);
    }
}

window.loadSceneData = payload => loadSceneData(payload).catch(showError);
window.fetchAndLoad = fetchAndLoad;

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}

animate();
fetchAndLoad();

window.addEventListener('resize', () => {
    camera.aspect = container.clientWidth / Math.max(container.clientHeight, 1);
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
    if (currentPayload) fitCameraToScene();
});