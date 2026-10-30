import { gridCoordinate } from '../core/gridCoordinate.js';
import { flightCurve, PathStyle } from '../objects/flightCurve.js';
import { createOffsetWaypoint } from '../utils/curveVariants.js';

const origin = new gridCoordinate(1, 5, 1);
const destination = new gridCoordinate(8, 3, 8);

export const flightCurves = [
  new flightCurve({
    start: origin,
    end: destination,
    color: 0x2962ff,
    style: PathStyle.SOLID,
    label: 'Main Route (Taken)',
  }),

  new flightCurve({
    start: origin,
    end: destination,
    waypoints: [createOffsetWaypoint(origin, destination, 2.5, 'y')],
    color: 0xffcc00,
    style: PathStyle.DASHED,
    label: 'Alternative Route A',
  }),

  new flightCurve({
    start: origin,
    end: destination,
    waypoints: [createOffsetWaypoint(origin, destination, -2.5, 'x')],
    color: 0xff3b30,
    style: PathStyle.DASHED,
    label: 'Alternative Route B',
  }),
];