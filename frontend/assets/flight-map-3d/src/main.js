import * as THREE from 'three';
import { createScene } from './core/scene.js';
import { createCamera } from './core/camera.js';
import { createRenderer } from './core/renderer.js';
import { createLights } from './core/lights.js';
import { createControls } from './core/controls.js';
import { createGridSystem } from './objects/grid.js';
import { gridConfig } from './data/gridConfig.js';
import { flightCurves } from './data/flightRoutes.js';
import { createPlaneTemplate, instantiatePlane, createPlaneAnimator } from './objects/plane.js';

const container = document.getElementById('app');

const scene = createScene();
const camera = createCamera();
const renderer = createRenderer(container);
const controls = createControls(camera, renderer.domElement);

createLights(scene);
scene.add(createGridSystem(gridConfig));

// Draw all curves immediately — these don't depend on the model
flightCurves.forEach(flightCurve => {
  scene.add(flightCurve.createMesh());
});

const planeAnimators = [];

// Load the model WITHOUT blocking the render loop
createPlaneTemplate()
  .then(planeTemplate => {
    console.log('Plane model loaded successfully:', planeTemplate);

    flightCurves
      .filter(fc => fc.taken)
      .forEach(flightCurve => {
        const planeMesh = instantiatePlane(planeTemplate);
        scene.add(planeMesh);
        planeAnimators.push(createPlaneAnimator(planeMesh, flightCurve.curve, 0.08));
      });
  })
  .catch(error => {
    console.error('Failed to load plane model:', error);
  });

const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);
  const delta = clock.getDelta();
  planeAnimators.forEach(update => update(delta));
  controls.update();
  renderer.render(scene, camera);
}

animate(); // starts immediately, independent of model loading

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});