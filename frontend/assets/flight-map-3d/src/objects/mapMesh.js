import * as THREE from 'three';

export function createMapMesh() {
  const geometry = new THREE.BoxGeometry(14, 0.5, 8); // wide, thin, flat slab
  const material = new THREE.MeshStandardMaterial({ color: 0x1a1a1a });

  const mesh = new THREE.Mesh(geometry, material);
  mesh.receiveShadow = true;
  mesh.position.y = 0;

  return mesh;
}