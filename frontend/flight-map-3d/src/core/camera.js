import * as THREE from 'three';

export function createCamera() {
  const camera = new THREE.PerspectiveCamera(
    45,                                   // field of view
    window.innerWidth / window.innerHeight, // aspect ratio
    0.1,                                  // near clipping plane
    1000                                  // far clipping plane
  );

  camera.position.set(0, 12, 18); // above and behind, looking down at an angle
  camera.lookAt(0, 0, 0);

  return camera;
}