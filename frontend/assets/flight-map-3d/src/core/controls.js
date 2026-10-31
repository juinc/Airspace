import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

export function createControls(camera, domElement, targetY = 0) {
    const controls = new OrbitControls(camera, domElement);
    controls.enableDamping = true; // smooth, inertia-like movement
    controls.dampingFactor = 0.05;
    controls.target.set(0, targetY, 0);
    controls.enablePan = false;
    controls.minPolarAngle = 0.05;
    controls.maxPolarAngle = Math.PI / 2 - 0.01;
    controls.minDistance = 4;
    controls.maxDistance = 24;
    controls.update();
    return controls;
}