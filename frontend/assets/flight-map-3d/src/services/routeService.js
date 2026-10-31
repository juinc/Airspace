import { mockRouteData } from '../data/mockRouteData.js';

export async function fetchRouteData() {
  // TEMPORARY: returns local mock data.
  // Later, replace this function's body with a real fetch, e.g.:
  //
  // const response = await fetch('https://your-backend.com/api/routes');
  // return response.json();
  //
  // Nothing outside this file needs to change when that happens.

  return Promise.resolve(mockRouteData);
}