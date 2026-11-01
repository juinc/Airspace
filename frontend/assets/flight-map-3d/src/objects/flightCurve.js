import * as THREE from 'three';

// ---------------------------------------------------------------------------
// Style table. sceneData.js imports PathStyle directly; uppercase keys are
// aliases so PathStyle.BASELINE and PathStyle.baseline both resolve.
// ---------------------------------------------------------------------------
export const PathStyle = {
    optimized: { color: 0xffb347, dashed: false, tube: true, radius: 1.6, opacity: 1.0 },
    baseline:  { color: 0x4dd8ff, dashed: true,  tube: false, dashSize: 7, gapSize: 5, opacity: 0.9 },
    previous:  { color: 0x7a8ea0, dashed: true,  tube: false, dashSize: 7, gapSize: 5, opacity: 0.7 },
};
PathStyle.OPTIMIZED = PathStyle.optimized;
PathStyle.BASELINE = PathStyle.baseline;
PathStyle.PREVIOUS = PathStyle.previous;

const TUBE_RADIUS = 1.6;
const DASH_SIZE = 7;
const GAP_SIZE = 5;
const NODE_MARKER_SIZE = 2.0;

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

function createSolidTube(waypoints, color, radius = TUBE_RADIUS) {
    const pts = toVector3s(waypoints);
    if (pts.length < 2) return null;
    const curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal');
    const segments = Math.min(600, Math.max(32, pts.length * 8));

    const tube = new THREE.Mesh(
        new THREE.TubeGeometry(curve, segments, radius, 10, false),
        new THREE.MeshBasicMaterial({ color }),
    );
    const glow = new THREE.Mesh(
        new THREE.TubeGeometry(curve, Math.min(400, segments), radius * 2.2, 10, false),
        new THREE.MeshBasicMaterial({
            color,
            transparent: true,
            opacity: 0.15,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        }),
    );
    const group = new THREE.Group();
    group.add(glow);
    group.add(tube);
    return group;
}

function createDashedLine(waypoints, color, dashSize = DASH_SIZE, gapSize = GAP_SIZE, opacity = 0.9) {
    const pts = toVector3s(waypoints);
    if (pts.length < 2) return null;
    const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineDashedMaterial({
            color,
            dashSize,
            gapSize,
            transparent: true,
            opacity,
        }),
    );
    line.computeLineDistances();
    return line;
}

function createNodeMarkers(waypoints, color) {
    const nodes = (waypoints || []).filter((w) => w?.node && Number.isFinite(w.x));
    if (nodes.length === 0) return null;
    const group = new THREE.Group();
    const geometry = new THREE.BoxGeometry(NODE_MARKER_SIZE, NODE_MARKER_SIZE, NODE_MARKER_SIZE);
    const material = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85 });
    for (const node of nodes) {
        const marker = new THREE.Mesh(geometry, material);
        marker.position.set(node.x, node.y ?? node.altitude_km * 4 ?? 0, node.z);
        group.add(marker);
    }
    return group;
}

/**
 * Legacy generic builder: accepts either a style key
 * ('optimized' | 'baseline' | 'previous') or a style object from PathStyle.
 */
export function createRoutePath(waypoints, style = 'baseline') {
    const s = typeof style === 'string'
        ? (PathStyle[style] || PathStyle.baseline)
        : (style || PathStyle.baseline);
    if (s.dashed) {
        return createDashedLine(waypoints, s.color, s.dashSize, s.gapSize, s.opacity);
    }
    return createSolidTube(waypoints, s.color, s.radius || TUBE_RADIUS);
}

/**
 * Builds every route from the payload: solid amber tube for the optimized
 * route, cyan dashed line + node markers for the baseline, gray dashed for
 * the previous route after a replan.
 */
export function createRouteGroup(routes = {}) {
    const group = new THREE.Group();
    group.name = 'routes';

    if (routes.previous_optimized?.length > 1) {
        const previous = createDashedLine(
            routes.previous_optimized,
            PathStyle.previous.color,
            PathStyle.previous.dashSize,
            PathStyle.previous.gapSize,
            PathStyle.previous.opacity,
        );
        if (previous) group.add(previous);
    }
    if (routes.baseline?.length > 1) {
        const baseline = createDashedLine(
            routes.baseline,
            PathStyle.baseline.color,
            PathStyle.baseline.dashSize,
            PathStyle.baseline.gapSize,
            PathStyle.baseline.opacity,
        );
        if (baseline) group.add(baseline);
    }
    if (routes.optimized?.length > 1) {
        const optimized = createSolidTube(routes.optimized, PathStyle.optimized.color);
        if (optimized) group.add(optimized);
        const markers = createNodeMarkers(routes.optimized, PathStyle.baseline.color);
        if (markers) group.add(markers);
    }
    return group;
}