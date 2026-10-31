/**
 * Groups points into vertical columns by (x, z), sorts each column by altitude,
 * then merges consecutive same-category points into single spans.
 *
 * Input:  [{ x, y, z, category }, ...]
 * Output: [{ x, z, category, yStart, yEnd, yCenter, layerCount }, ...]
 */
export function buildWeatherColumns(points, columnPrecision = 2) {
  const columns = new Map();

  points.forEach(point => {
    const key = columnKey(point.x, point.z, columnPrecision);
    if (!columns.has(key)) columns.set(key, []);
    columns.get(key).push(point);
  });

  const spans = [];
  columns.forEach(columnPoints => {
    columnPoints.sort((a, b) => a.y - b.y);
    spans.push(...mergeConsecutiveByCategory(columnPoints));
  });

  return spans;
}

function mergeConsecutiveByCategory(sortedPoints) {
  const spans = [];
  let current = null;

  sortedPoints.forEach(point => {
    if (current && current.category === point.category) {
      current.yEnd = point.y;
      current.layerCount += 1;
    } else {
      if (current) spans.push(current);
      current = {
        x: point.x,
        z: point.z,
        category: point.category,
        yStart: point.y,
        yEnd: point.y,
        layerCount: 1,
      };
    }
  });
  if (current) spans.push(current);

  return spans.map(span => ({ ...span, yCenter: (span.yStart + span.yEnd) / 2 }));
}

function columnKey(x, z, precision) {
  return `${x.toFixed(precision)},${z.toFixed(precision)}`;
}