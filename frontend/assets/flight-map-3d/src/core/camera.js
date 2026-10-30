import * as THREE from 'three';

export function createCamera() {
  const camera = new THREE.PerspectiveCamera(
    45,
    window.innerWidth / window.innerHeight,
    0.1,
    1000
  );

  camera.position.set(14, 14, 20);
  camera.lookAt(0, 0, 0);

  return camera;
}