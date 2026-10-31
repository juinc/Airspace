import * as THREE from 'three';
import { loadModel } from '../loaders/modelLoader.js';
import { planeModelConfig } from '../data/modelConfig.js';

export async function createPlaneTemplate() {
  const model = await loadModel(planeModelConfig.path);
  model.scale.setScalar(planeModelConfig.scale);
  return model;
}

export function instantiatePlane(template) {
  const mesh = template.clone(true);
  mesh.castShadow = true;
  mesh.traverse(child => {
    if (child.isMesh) child.castShadow = true;
  });
  return mesh;
}

export function createPlaneAnimator(planeMesh, curve, speed = 0.05) {
  let t = 0;

  return function update(delta) {
    t += delta * speed;
    if (t > 1) t = 0;

    const position = curve.getPointAt(t);
    const lookAtPoint = curve.getPointAt(Math.min(t + 0.01, 1));

    planeMesh.position.copy(position);
    planeMesh.lookAt(lookAtPoint);
    planeMesh.rotateY(planeModelConfig.rotationOffsetY);
  };
}