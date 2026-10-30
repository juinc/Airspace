import * as THREE from 'three';

export function createMiniCubeGeometry(cubeSize) {
  return new THREE.BoxGeometry(cubeSize, cubeSize, cubeSize);
}

export function createMiniCubeMaterial() {
  return new THREE.MeshBasicMaterial({
    color: 0x66ffcc,
    wireframe: true,
  });
}