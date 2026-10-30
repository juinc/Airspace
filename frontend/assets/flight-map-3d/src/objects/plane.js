import * as THREE from 'three';

export function createPlane() {
  const geometry = new THREE.ConeGeometry(0.15, 0.5, 8);
  const material = new THREE.MeshStandardMaterial({ color: 0xffffff });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.rotation.x = Math.PI / 2; // point the cone forward instead of up
  mesh.castShadow = true;
  return mesh;
}

export function createPlaneAnimator(planeMesh, curve, speed = 0.05) {
  let t = 0;

  return function update(delta) {
    t += delta * speed;
    if (t > 1) t = 0; // loop back to start of route

    const position = curve.getPointAt(t);
    const lookAtPoint = curve.getPointAt(Math.min(t + 0.01, 1));

    planeMesh.position.copy(position);
    planeMesh.lookAt(lookAtPoint);
  };
}