import { gridCoordinate } from '../core/gridCoordinate.js';

export function createOffsetWaypoint(start, end, offsetAmount, axis = 'y') {
  const mid = {
    x: (start.x + end.x) / 2,
    y: (start.y + end.y) / 2,
    z: (start.z + end.z) / 2,
  };

  mid[axis] += offsetAmount;

  return new gridCoordinate(mid.x, mid.y, mid.z);
}