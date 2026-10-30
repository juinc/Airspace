import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

export function createControls(camera, domElement) {
  const controls = new OrbitControls(camera, domElement);
  controls.enableDamping = true; // smooth, inertia-like movement
  controls.dampingFactor = 0.05;
  return controls;
}