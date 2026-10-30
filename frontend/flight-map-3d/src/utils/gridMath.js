export function getCubePosition(index, gridConfig) {
  const { size, cubeSize, spacing } = gridConfig;
  const step = cubeSize + spacing;
  const offset = ((size - 1) * step) / 2; // centers the whole grid at the origin

  return {
    x: index.x * step - offset,
    y: index.y * step - offset,
    z: index.z * step - offset,
  };
}