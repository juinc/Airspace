import * as THREE from 'three';
import { createScene } from './core/scene.js';
import { createCamera } from './core/camera.js';
import { createRenderer } from './core/renderer.js';
import { createLights } from './core/lights.js';
import { createControls } from './core/controls.js';
import { createMapMesh } from './objects/mapMesh.js';
import { createFlightPathLine } from './objects/flightPath.js';
import { createPlane, createPlaneAnimator } from './objects/plane.js';
import { createCurve } from './utils/curveHelpers.js';
import { routes } from './data/routes.js';

const container = document.getElementById('app');

const scene = createScene();
const camera = createCamera();
const renderer = createRenderer(container);
const controls = createControls(camera, renderer.domElement);

createLights(scene);
scene.add(createMapMesh());

// Build flight paths + planes from route data
const planeAnimators = [];

routes.forEach(route => {
  const curve = createCurve(route.points);

  const pathMesh = createFlightPathLine(curve, route.color);
  scene.add(pathMesh);

  const planeMesh = createPlane();
  scene.add(planeMesh);

  const animator = createPlaneAnimator(planeMesh, curve, 0.08);
  planeAnimators.push(animator);
});

// Animation loop
const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);

  const delta = clock.getDelta();
  planeAnimators.forEach(update => update(delta));

  controls.update();
  renderer.render(scene, camera);
}

animate();

// Handle window resize
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});