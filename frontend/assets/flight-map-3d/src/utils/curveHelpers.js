import * as THREE from 'three';

export function createCurve(points) {
  const vectors = points.map(p => new THREE.Vector3(p[0], p[1], p[2]));
  return new THREE.CatmullRomCurve3(vectors);
}