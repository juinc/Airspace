import * as THREE from 'three';

export const PathStyle = {
  SOLID: 'solid',
  DASHED: 'dashed',
};

let autoId = 0;

export class FlightCurve {
  constructor({
    start,
    end,
    waypoints = [],
    color = 0xffffff,
    style = PathStyle.SOLID,
    taken = style === PathStyle.SOLID,
    label = '',
  }) {
    if (!start.isValid() || !end.isValid()) {
      console.warn(`FlightCurve "${label}" has an out-of-bounds endpoint.`);
    }

    this.id = `path-${autoId++}`;
    this.start = start;
    this.end = end;
    this.waypoints = waypoints;
    this.color = color;
    this.style = style;
    this.taken = taken;
    this.label = label;

    this.curve = this._buildCurve();
  }

  static fromPath({ path, ...options }) {
    if (!Array.isArray(path) || path.length < 2) {
      throw new TypeError('A flight path must contain at least two coordinates.');
    }

    return new FlightCurve({
      ...options,
      start: path[0],
      end: path[path.length - 1],
      waypoints: path.slice(1, -1),
    });
  }

  _buildCurve() {
    const points = [this.start, ...this.waypoints, this.end].map(gc =>
      gc.toWorldPosition()
    );
    return new THREE.CatmullRomCurve3(points);
  }

  createMesh() {
    return this.style === PathStyle.DASHED
      ? this._createDashedLine()
      : this._createSolidTube();
  }

  _createSolidTube() {
    const geometry = new THREE.TubeGeometry(this.curve, 64, 0.04, 8, false);
    const material = new THREE.MeshBasicMaterial({ color: this.color });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.flightCurveId = this.id;
    return mesh;
  }

  _createDashedLine() {
    const points = this.curve.getPoints(100);
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineDashedMaterial({
      color: this.color,
      dashSize: 0.15,
      gapSize: 0.08,
    });
    const line = new THREE.Line(geometry, material);
    line.computeLineDistances(); // mandatory for dashing to work
    line.userData.flightCurveId = this.id;
    return line;
  }
}

// Backwards-compatible alias for any existing lowercase imports.
export { FlightCurve as flightCurve };