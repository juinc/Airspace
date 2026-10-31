export function pointsFromGrid(grid) {
  const points = [];
  grid.forEach(gridPoint => {
    if (!Number.isFinite(gridPoint.x) || !Number.isFinite(gridPoint.z)) return;
    Object.values(gridPoint.levels || {}).forEach(level => {
      if (!level || !Number.isFinite(level.y)) return;
      points.push({
        x: gridPoint.x,
        y: level.y,
        z: gridPoint.z,
        category: scoreToCategory(level.exposure_score),
      });
    });
  });
  return points;
}

function scoreToCategory(score) {
  if (!Number.isFinite(score)) return 'unknown';
  if (score <= 25) return 'low';
  if (score <= 50) return 'moderate';
  if (score <= 75) return 'elevated';
  return 'high';
}