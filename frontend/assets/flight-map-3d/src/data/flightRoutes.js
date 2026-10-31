import { GridCoordinate } from '../core/gridCoordinate.js';
import { FlightCurve } from '../objects/FlightCurve.js';
//import { simplifyPath } from '../utils/pathSimplify.js';
import { fetchRouteData } from '../services/routeService.js';

export async function buildFlightCurves() {
  const routeData = await fetchRouteData();

  return routeData.map(route => {
    const path = route.path.map(GridCoordinate.fromPlain);
    const simplifiedPath = simplifyPath(path);

    return FlightCurve.fromPath({
      path: simplifiedPath,
      color: route.color,
      style: route.style,
      taken: route.taken,
      label: route.label,
    });
  });
}