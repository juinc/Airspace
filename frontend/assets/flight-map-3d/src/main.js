import * as THREE from 'three';
import { createScene } from './core/scene.js';
import { createCamera } from './core/camera.js';
import { createRenderer } from './core/renderer.js';
import { createLights } from './core/lights.js';
import { createControls } from './core/controls.js';
import { createGridSystem } from './objects/grid.js';
import { gridConfig } from './data/gridConfig.js';
import { buildFlightCurves } from './data/flightRoutes.js';
import { createPlaneTemplate, instantiatePlane, createPlaneAnimator } from './objects/plane.js';

const container = document.getElementById('app');

const scene = createScene();
const camera = createCamera();
const renderer = createRenderer(container);
const controls = createControls(camera, renderer.domElement);

createLights(scene);
scene.add(createGridSystem(gridConfig));

const planeAnimators = [];

// Load route data (currently mock, later real backend) — doesn't block rendering
buildFlightCurves()
  .then(flightCurves => {
    console.log(`Loaded ${flightCurves.length} flight curves.`);

    flightCurves.forEach(flightCurve => {
      scene.add(flightCurve.createMesh());
    });

    return createPlaneTemplate().then(planeTemplate => {
      flightCurves
        .filter(fc => fc.taken)
        .forEach(flightCurve => {
          const planeMesh = instantiatePlane(planeTemplate);
          scene.add(planeMesh);
          planeAnimators.push(createPlaneAnimator(planeMesh, flightCurve.curve, 0.08));
        });
    });
  })
  .catch(error => {
    console.error('Failed to build flight curves or load plane model:', error);
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