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
        if (
            (typeof start.isValid === 'function' && !start.isValid()) ||
            (typeof end.isValid === 'function' && !end.isValid())
        ) {
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
            typeof gc.toWorldPosition === 'function' ?
            gc.toWorldPosition() :
            gc instanceof THREE.Vector3 ?
            gc.clone() :
            new THREE.Vector3(gc.x, gc.y, gc.z)
        );
        return new THREE.CatmullRomCurve3(points);
    }

    createMesh() {
        return this.style === PathStyle.DASHED ?
            this._createDashedLine() :
            this._createSolidTube();
    }

    _createSolidTube() {
        const geometry = new THREE.TubeGeometry(this.curve, 64, 4, 8, false);
        const material = new THREE.MeshBasicMaterial({ color: this.color, depthTest: false });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.renderOrder = 10;
        mesh.userData.flightCurveId = this.id;
        return mesh;
    }

    _createDashedLine() {
        const group = new THREE.Group();
        const material = new THREE.MeshBasicMaterial({ color: this.color, depthTest: false });
        const length = this.curve.getLength();
        const dashLength = 6;
        const patternLength = 10;

        for (let offset = 0; offset < length; offset += patternLength) {
            const end = Math.min(offset + dashLength, length);
            const pointCount = Math.max(2, Math.ceil((end - offset) / 2));
            const points = Array.from({ length: pointCount + 1 }, (_, index) => {
                const distance = offset + ((end - offset) * index) / pointCount;
                return this.curve.getPointAt(distance / length);
            });
            const segmentCurve = new THREE.CatmullRomCurve3(points);
            const geometry = new THREE.TubeGeometry(segmentCurve, pointCount, 4, 8, false);
            const segment = new THREE.Mesh(geometry, material);
            segment.renderOrder = 10;
            group.add(segment);
        }

        group.userData.flightCurveId = this.id;
        return group;
    }
}

// Backwards-compatible alias for any existing lowercase imports.
export { FlightCurve as flightCurve };