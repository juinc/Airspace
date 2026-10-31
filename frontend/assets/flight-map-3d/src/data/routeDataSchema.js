/**
 * Expected shape of route data, whether from mock JSON or the backend API.
 *
 * {
 *   id: string,
 *   label: string,
 *   color: number,        // hex color, e.g. 0x2962ff
 *   style: 'solid' | 'dashed',
 *   taken: boolean,
 *   path: [ { x: number, y: number, z: number }, ... ]  // already-optimized, in order
 * }
 */