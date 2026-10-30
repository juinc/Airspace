import * as THREE from 'three';
import { createScene } from './core/scene.js';
import { createCamera } from './core/camera.js';
import { createRenderer } from './core/renderer.js';
import { createLights } from './core/lights.js';
import { createControls } from './core/controls.js';
import { createGridSystem } from './objects/grid.js';
import { gridConfig } from './data/gridConfig.js';
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

// Grid system replaces the old flat slab placeholder
scene.add(createGridSystem(gridConfig));

// Flight paths/planes stay as before — they now fly inside the grid
const planeAnimators = [];

routes.forEach(route => {
  const curve = createCurve(route.points);

  scene.add(createFlightPathLine(curve, route.color));

  const planeMesh = createPlane();
  scene.add(planeMesh);

  planeAnimators.push(createPlaneAnimator(planeMesh, curve, 0.08));
});

const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);
  const delta = clock.getDelta();
  planeAnimators.forEach(update => update(delta));
  controls.update();
  renderer.render(scene, camera);
}

animate();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});