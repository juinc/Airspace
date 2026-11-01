// Must mirror grid/coordinates.py — the backend bakes scene y with this
// factor; used as a fallback when the payload only carries altitude_km.
const VERTICAL_EXAGGERATION = 4;

/**
 * Adapts the backend weather grid into renderable 3D points.
 *
 * Robust to missing fields: scene y falls back to altitude_km * exaggeration,
 * and a level with no exposure score inherits the column's score. A missing
 * score renders as light cloud ('low') instead of vanishing — an empty sky
 * is always a bug, calm weather is not.
 */
export function pointsFromGrid(grid) {
  const points = [];
  grid.forEach(gridPoint => {
    if (!Number.isFinite(gridPoint.x) || !Number.isFinite(gridPoint.z)) return;
    const columnScore = Number.isFinite(gridPoint.exposure_score)
        ? gridPoint.exposure_score
        : null;
    Object.values(gridPoint.levels || {}).forEach(level => {
      if (!level) return;
      const y = Number.isFinite(level.y)
          ? level.y
          : Number.isFinite(level.altitude_km)
              ? level.altitude_km * VERTICAL_EXAGGERATION
              : null;
      if (!Number.isFinite(y)) return;
      const score = Number.isFinite(level.exposure_score)
          ? level.exposure_score
          : columnScore;
      points.push({
        x: gridPoint.x,
        y,
        z: gridPoint.z,
        score,
        category: scoreToCategory(score),
      });
    });
  });
  return points;
}

function scoreToCategory(score) {
  if (!Number.isFinite(score)) return 'low';
  if (score <= 25) return 'low';
  if (score <= 50) return 'moderate';
  if (score <= 75) return 'elevated';
  return 'high';
}