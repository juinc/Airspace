import * as THREE from 'three';

export function createGridBoundary(gridConfig) {
  const { size, cubeSize, spacing } = gridConfig;
  const step = cubeSize + spacing;
  const outerSize = size * step - spacing;

  const geometry = new THREE.BoxGeometry(outerSize, outerSize, outerSize);
  const edges = new THREE.EdgesGeometry(geometry);
  const material = new THREE.LineBasicMaterial({ color: 0xffffff });

  return new THREE.LineSegments(edges, material);
}