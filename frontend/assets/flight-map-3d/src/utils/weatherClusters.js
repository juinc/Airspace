/**
 * Flood-fill unification of weather cells.
 *
 * 1. Build vertical spans per (x, z) column (same-category consecutive layers).
 * 2. Merge spans that share a category, are horizontally adjacent and
 *    vertically overlapping, into clusters via union-find.
 * 3. Each cluster keeps its member cells so the renderer can place one
 *    cloud puff per cell (no stretched blobs).
 *
 * Input:  [{ x, y, z, category }, ...]
 * Output: [{ category, cells: [{x,y,z}...], x, z, yCenter,
 *           width, depth, height, layerCount, cellCount }, ...]
 */
export function buildWeatherClusters(points, cellStepX, cellStepZ, columnPrecision = 2) {
  if (!Array.isArray(points) || points.length === 0) return [];
  if (!Number.isFinite(cellStepX) || !Number.isFinite(cellStepZ)) return [];

  const columns = new Map();
  points.forEach(point => {
    const key = columnKey(point.x, point.z, columnPrecision);
    if (!columns.has(key)) columns.set(key, []);
    columns.get(key).push(point);
  });

  // --- Vertical spans per column ---
  const spans = [];
  columns.forEach(columnPoints => {
    columnPoints.sort((a, b) => a.y - b.y);
    let current = null;
    columnPoints.forEach(point => {
      if (current && current.category === point.category) {
        current.yEnd = point.y;
        current.layerCount += 1;
        current.points.push(point);
      } else {
        if (current) spans.push(current);
        current = {
          key: columnKey(point.x, point.z, columnPrecision),
          x: point.x,
          z: point.z,
          category: point.category,
          yStart: point.y,
          yEnd: point.y,
          layerCount: 1,
          points: [point],
        };
      }
    });
    if (current) spans.push(current);
  });

  if (spans.length === 0) return [];

  // --- Union-find over spans ---
  const parent = spans.map((_, i) => i);
  const find = i => (parent[i] === i ? i : (parent[i] = find(parent[i])));
  const union = (a, b) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent[ra] = rb;
  };

  const spansByColumn = new Map();
  spans.forEach((span, i) => {
    const mapKey = span.key + '|' + span.category;
    if (!spansByColumn.has(mapKey)) spansByColumn.set(mapKey, []);
    spansByColumn.get(mapKey).push({ index: i, span });
  });

  const neighborOffsets = [
    [cellStepX, 0],
    [-cellStepX, 0],
    [0, cellStepZ],
    [0, -cellStepZ],
  ];

  spans.forEach((span, i) => {
    neighborOffsets.forEach(([dx, dz]) => {
      const nKey = columnKey(span.x + dx, span.z + dz, columnPrecision) + '|' + span.category;
      const neighbors = spansByColumn.get(nKey);
      if (!neighbors) return;
      neighbors.forEach(({ index: j, span: nSpan }) => {
        if (verticallyOverlaps(span, nSpan)) union(i, j);
      });
    });
  });

  // --- Collect clusters ---
  const clusters = new Map();
  spans.forEach((span, i) => {
    const root = find(i);
    if (!clusters.has(root)) {
      clusters.set(root, {
        category: span.category,
        minX: span.x,
        maxX: span.x,
        minZ: span.z,
        maxZ: span.z,
        minY: span.yStart,
        maxY: span.yEnd,
        layerCount: 0,
        cells: [],
      });
    }
    const c = clusters.get(root);
    c.minX = Math.min(c.minX, span.x);
    c.maxX = Math.max(c.maxX, span.x);
    c.minZ = Math.min(c.minZ, span.z);
    c.maxZ = Math.max(c.maxZ, span.z);
    c.minY = Math.min(c.minY, span.yStart);
    c.maxY = Math.max(c.maxY, span.yEnd);
    c.layerCount = Math.max(c.layerCount, span.layerCount);
    c.cells.push(...span.points);
  });

  return [...clusters.values()].map(c => ({
    category: c.category,
    cells: c.cells,
    x: (c.minX + c.maxX) / 2,
    z: (c.minZ + c.maxZ) / 2,
    yCenter: (c.minY + c.maxY) / 2,
    width: c.maxX - c.minX + cellStepX,
    depth: c.maxZ - c.minZ + cellStepZ,
    height: c.maxY - c.minY,
    layerCount: c.layerCount,
    cellCount: c.cells.length,
  }));
}

function verticallyOverlaps(a, b) {
  return a.yStart <= b.yEnd && b.yStart <= a.yEnd;
}

function columnKey(x, z, precision) {
  return `${x.toFixed(precision)},${z.toFixed(precision)}`;
}