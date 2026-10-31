import * as THREE from 'three';

export function createWeatherSpanMarkers(spans, weatherMeshKit, options = {}) {
  const { stretchMode = 'scale' } = options;
  const group = new THREE.Group();
  const spansByCategory = groupByCategory(spans);

  Object.entries(spansByCategory).forEach(([category, categorySpans]) => {
    if (categorySpans.length === 0) return;
    const parts = weatherMeshKit[category];
    if (!parts || parts.length === 0) return;

    parts.forEach(part => {
      const instancedMesh = new THREE.InstancedMesh(part.geometry, part.material, categorySpans.length);
      const translation = new THREE.Matrix4();
      const scaleMatrix = new THREE.Matrix4();
      const finalMatrix = new THREE.Matrix4();

      categorySpans.forEach((span, index) => {
        const stretch = stretchMode === 'scale' ? Math.max(1, span.layerCount) : 1;
        translation.makeTranslation(span.x, span.yCenter, span.z);
        scaleMatrix.makeScale(1, stretch, 1);
        finalMatrix.multiplyMatrices(translation, scaleMatrix);
        finalMatrix.multiply(part.matrix);
        instancedMesh.setMatrixAt(index, finalMatrix);
      });

      instancedMesh.instanceMatrix.needsUpdate = true;
      group.add(instancedMesh);
    });
  });

  return group;
}

function groupByCategory(spans) {
  const grouped = { low: [], moderate: [], elevated: [], high: [], unknown: [] };
  spans.forEach(span => grouped[span.category]?.push(span));
  return grouped;
}