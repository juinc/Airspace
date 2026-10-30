import * as THREE from 'three';

export function createLights(scene) {
  const ambient = new THREE.AmbientLight(0xffffff, 0.6);
  scene.add(ambient);

  const directional = new THREE.DirectionalLight(0xffffff, 1);
  directional.position.set(10, 20, 10);
  directional.castShadow = true;

  // Shadow camera bounds — how large an area can cast/receive shadows
  directional.shadow.camera.left = -20;
  directional.shadow.camera.right = 20;
  directional.shadow.camera.top = 20;
  directional.shadow.camera.bottom = -20;

  scene.add(directional);
}