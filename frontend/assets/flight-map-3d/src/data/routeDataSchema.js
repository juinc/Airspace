/**
 * Expected shape of route data, whether from mock JSON or the backend API.
 *
 * {
 *   id: string,
 *   label: string,
 *   color: number,        // hex color, e.g. 0x2962ff
 *   style: 'solid' | 'dashed',
 *   taken: boolean,
 *   path: [ { x: number, y: number, z: number }, ... ]  // ordered waypoint path
 *   // Or provide reusable ordered waypoint paths that join at shared endpoints:
 *   segments?: [ [ { x, y, z }, ... ], ... ]
 * }
 */