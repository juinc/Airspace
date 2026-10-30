import * as THREE from 'three';

export function createFlightPathLine(curve, color) {
  const tubeGeometry = new THREE.TubeGeometry(curve, 64, 0.04, 8, false);
  const material = new THREE.MeshBasicMaterial({ color });
  return new THREE.Mesh(tubeGeometry, material);
}