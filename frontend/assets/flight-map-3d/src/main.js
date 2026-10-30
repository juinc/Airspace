import * as THREE from 'three';
import { createScene } from './core/scene.js';
import { createCamera } from './core/camera.js';
import { createRenderer } from './core/renderer.js';
import { createLights } from './core/lights.js';
import { createControls } from './core/controls.js';
import { createGridSystem } from './objects/grid.js';
import { gridConfig } from './data/gridConfig.js';
import { createPlane, createPlaneAnimator } from './objects/plane.js';
import { flightCurves } from './data/flightRoutes.js';

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

flightCurves.forEach(flightCurve => {
  scene.add(flightCurve.createMesh());

  if (flightCurve.taken) {
    const planeMesh = createPlane();
    scene.add(planeMesh);
    planeAnimators.push(createPlaneAnimator(planeMesh, flightCurve.curve, 0.08));
  }
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