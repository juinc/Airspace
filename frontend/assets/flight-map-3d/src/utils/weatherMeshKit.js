import * as THREE from 'three';
import { loadModel } from '../loaders/modelLoader.js';
import { weatherModelConfig } from '../data/weatherModelConfig.js';

let cachedKitPromise = null;

export function loadWeatherMeshKit() {
  if (cachedKitPromise) return cachedKitPromise;
  cachedKitPromise = buildKit();
  return cachedKitPromise;
}

async function buildKit() {
  const kit = {};

  await Promise.all(
    Object.entries(weatherModelConfig).map(async ([category, config]) => {
      const rawModel = await loadModel(config.path);
      const container = normalizeToUnitCube(rawModel, config);
      container.updateWorldMatrix(true, true);

      const parts = [];
      container.traverse(child => {
        if (!child.isMesh) return;

        child.geometry.userData.shared = true;
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        materials.forEach(m => { m.userData.shared = true; });

        parts.push({
          geometry: child.geometry,
          material: child.material,
          matrix: child.matrixWorld.clone(),
        });
      });

      kit[category] = parts;
    })
  );

  return kit;
}

function normalizeToUnitCube(rawModel, config) {
  if (config.rotationOffsetY) rawModel.rotateY(config.rotationOffsetY);

  const box = new THREE.Box3().setFromObject(rawModel);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());

  const safeSize = new THREE.Vector3(size.x || 1, size.y || 1, size.z || 1);

  // Shift the model so its bounding-box center sits at local origin.
  rawModel.position.sub(center);

  // Wrap in a container and scale IT, not the model directly — this keeps
  // the center-then-scale math correct regardless of operation order.
  const container = new THREE.Group();
  container.add(rawModel);

  const fillRatio = config.fillRatio ?? 1;
  container.scale.set(
    (1 / safeSize.x) * fillRatio,
    (1 / safeSize.y) * fillRatio,
    (1 / safeSize.z) * fillRatio
  );

  return container;
}