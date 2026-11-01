import * as THREE from 'three';

// Style constants used by sceneData.js: PathStyle.SOLID / PathStyle.DASHED.
export const PathStyle = {
    SOLID: { dashed: false, radius: 1.6, opacity: 1.0 },
    DASHED: { dashed: true, dashSize: 7, gapSize: 5, opacity: 0.9 },
};

const GLOW_OPACITY = 0.15;

export function disposeDeep(root) {
    if (!root) return;
    root.traverse((obj) => {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) {
            (Array.isArray(obj.material) ? obj.material : [obj.material])
                .forEach((m) => m.dispose());
        }
    });
}

function toVector3s(waypoints) {
    return (waypoints || [])
        .filter((w) => Number.isFinite(w?.x) && Number.isFinite(w?.z))
        .map((w) => {
            const y = Number.isFinite(w.y)
                ? w.y
                : (Number.isFinite(w.altitude_km) ? w.altitude_km * 4 : 0);
            return new THREE.Vector3(w.x, y, w.z);
        });
}

/**
 * FlightCurve — wraps a waypoint list in a smooth Catmull-Rom curve and can
 * build its mesh. The backend now sends densely-sampled waypoints (max 8 km
 * apart), so drawing through every point yields a smooth flight arc with no
 * elbows by construction.
 */
export class FlightCurve {
    constructor(waypoints, style = PathStyle.DASHED, color = 0x4dd8ff) {
        this.waypoints = waypoints || [];
        this.style = style || PathStyle.DASHED;
        this.color = color;
        this.points = toVector3s(this.waypoints);
        this.curve = this.points.length >= 2
            ? new THREE.CatmullRomCurve3(this.points, false, 'centripetal')
            : null;
    }

    static fromPath({ path, waypoints, color = 0x4dd8ff, style = PathStyle.DASHED } = {}) {
        return new FlightCurve(path || waypoints || [], style, color);
    }

    createMesh() {
        const group = new THREE.Group();
        if (!this.curve || this.points.length < 2) return group;

        if (this.style.dashed) {
            const line = new THREE.Line(
                new THREE.BufferGeometry().setFromPoints(this.points),
                new THREE.LineDashedMaterial({
                    color: this.color,
                    dashSize: this.style.dashSize ?? 7,
                    gapSize: this.style.gapSize ?? 5,
                    transparent: true,
                    opacity: this.style.opacity ?? 0.9,
                }),
            );
            line.computeLineDistances();
            group.add(line);
        } else {
            const radius = this.style.radius ?? 1.6;
            const segments = Math.min(600, Math.max(64, this.points.length * 8));
            const tube = new THREE.Mesh(
                new THREE.TubeGeometry(this.curve, segments, radius, 10, false),
                new THREE.MeshBasicMaterial({ color: this.color }),
            );
            const glow = new THREE.Mesh(
                new THREE.TubeGeometry(this.curve, Math.min(400, segments), radius * 2.2, 10, false),
                new THREE.MeshBasicMaterial({
                    color: this.color,
                    transparent: true,
                    opacity: GLOW_OPACITY,
                    blending: THREE.AdditiveBlending,
                    depthWrite: false,
                }),
            );
            group.add(glow);
            group.add(tube);
        }
        return group;
    }
}

export default FlightCurve;