export const mockRouteData = [
  {
    id: 'route-1',
    label: 'Main Route (Taken)',
    color: 0x2962ff,
    style: 'solid',
    taken: true,
    path: [
      { x: 0, y: 2, z: 0 },
      { x: 2, y: 2, z: 1 },
      { x: 5, y: 4, z: 4 },
      { x: 7, y: 6, z: 7 },
      { x: 9, y: 7, z: 9 },
    ],
  },
  {
    id: 'route-2',
    label: 'Alternative Route A',
    color: 0xffcc00,
    style: 'dashed',
    taken: false,
    path: [
      { x: 0, y: 2, z: 0 },
      { x: 3, y: 0, z: 2 },
      { x: 5, y: 0, z: 5 },
      { x: 9, y: 7, z: 9 },
    ],
  },
  {
    id: 'route-3',
    label: 'Alternative Route B',
    color: 0xff3b30,
    style: 'dashed',
    taken: false,
    path: [
      { x: 0, y: 2, z: 0 },
      { x: 2, y: 9, z: 3 },
      { x: 4, y: 9, z: 6 },
      { x: 9, y: 7, z: 9 },
    ],
  },
];