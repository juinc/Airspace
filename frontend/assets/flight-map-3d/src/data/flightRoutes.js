import { GridCoordinate } from '../core/gridCoordinate.js';
import { FlightCurve } from '../objects/flightCurve.js';
import { fetchRouteData } from '../services/routeService.js';

/**
 * Join reusable waypoint segments into one ordered path, dropping a repeated
 * shared endpoint where one segment ends exactly where the next begins.
 */
export function composeTrajectorySegments(segments) {
  if (!Array.isArray(segments)) return [];

  return segments.reduce((path, segment) => {
    if (!Array.isArray(segment)) return path;

    const points = segment.map(point =>
      point instanceof GridCoordinate ? point : GridCoordinate.fromPlain(point)
    );
    if (path.length && points.length && path[path.length - 1].equals(points[0])) {
      points.shift();
    }
    return path.concat(points);
  }, []);
}

export async function buildFlightCurves(routeInput) {
  const routeData = routeInput === undefined ? await fetchRouteData() : routeInput;
  if (!Array.isArray(routeData)) {
    throw new TypeError('Route input must be an array.');
  }

  return routeData.flatMap(route => {
    if (!route || typeof route !== 'object') return [];

    const segments = Array.isArray(route.segments)
      ? route.segments
      : [route.path];
    const path = composeTrajectorySegments(segments);
    if (path.length < 2) return [];

    return [
      FlightCurve.fromPath({
        path,
        color: route.color,
        style: route.style,
        taken: route.taken,
        label: route.label,
      }),
    ];
  });
}