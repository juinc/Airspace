import * as THREE from 'three';
import { FlightCurve, PathStyle } from './objects/flightCurve.js';
import { createPlaneAnimator, instantiatePlane } from './objects/plane.js';

const EXPOSURE_COLORS = {
    low: 0x35A66B,
    moderate: 0xC9BE37,
    elevated: 0xE68A37,
    high: 0xCE4C4C,
    unknown: 0x888888,
};

const EVENT_COLORS = {
    rain: 0x3399ff,
    thunderstorm: 0xffaa00,
    severe_storm: 0xff2200,
    default: 0xffffff,
};
const PRESSURE_LEVEL_COLORS = [0x43c1c6, 0x7abf78, 0xe2b65f, 0xe77c68];

export function createSceneDataGroup(payload, planeTemplate, initialProgress = 0) {
    const group = new THREE.Group();
    renderGrid(payload.grid || [], group);
    renderAltitudeLayers(payload.grid || [], group);
    renderEvents(payload.events || [], group);
    renderAirports(payload.airports || [], group);

    const routes = payload.routes || {};
    renderRoute(routes.baseline, 0x3399ff, PathStyle.DASHED, group);
    if (payload.weather_update?.replanned) {
        renderRoute(routes.previous_optimized, 0x9aa6b2, PathStyle.DASHED, group);
    }
    const optimizedCurve = renderRoute(routes.optimized, 0xff6633, PathStyle.SOLID, group);
    if (optimizedCurve) {
        const plane = instantiatePlane(planeTemplate);
        const planeBounds = new THREE.Box3().setFromObject(plane);
        const planeSize = planeBounds.getSize(new THREE.Vector3());
        const largestDimension = Math.max(planeSize.x, planeSize.y, planeSize.z);
        if (largestDimension > 0) plane.scale.multiplyScalar(40);
        plane.traverse(object => {
            if (!object.isMesh) return;
            object.renderOrder = 10000;
            const materials = Array.isArray(object.material) ? object.material : [object.material];
            materials.forEach(material => {
                material.depthTest = false;
                material.depthWrite = false;
            });
        });
        group.add(plane);
        const updatePlane = createPlaneAnimator(
            plane,
            optimizedCurve.curve,
            0.035,
            initialProgress,
        );
        group.userData.update = updatePlane;
        group.userData.getFlightProgress = updatePlane.getProgress;
    }
    return group;
}

export function disposeSceneDataGroup(group) {
    const geometries = new Set();
    const materials = new Set();
    const textures = new Set();

    group.traverse(object => {
        if (object.geometry) geometries.add(object.geometry);
        if (Array.isArray(object.material)) {
            object.material.forEach(material => collectMaterial(material, materials, textures));
        } else if (object.material) {
            collectMaterial(object.material, materials, textures);
        }
    });

    geometries.forEach(geometry => geometry.dispose());
    materials.forEach(material => material.dispose());
    textures.forEach(texture => texture.dispose());
}

export function alignAirportsToMap(group, mapMesh) {
    const airportMarkers = [];
    group.traverse(object => {
        if (object.userData.isAirportMarker) airportMarkers.push(object);
    });
    if (airportMarkers.length === 0) return;

    mapMesh.updateWorldMatrix(true, true);
    const mapBounds = new THREE.Box3().setFromObject(mapMesh);
    const raycaster = new THREE.Raycaster();
    raycaster.far = mapBounds.getSize(new THREE.Vector3()).y + 2;

    airportMarkers.forEach(marker => {
        raycaster.ray.origin.set(marker.position.x, mapBounds.max.y + 1, marker.position.z);
        raycaster.ray.direction.set(0, -1, 0);
        const surface = raycaster.intersectObject(mapMesh, true)[0];
        if (surface) marker.position.y = surface.point.y + marker.userData.markerRadius;
    });
}

export function renderMetrics(metrics) {
    const setText = (id, value, suffix = '') => {
        const element = document.getElementById(id);
        if (element) element.textContent = `${value == null ? 'N/A' : value}${suffix}`;
    };

    const baseline = metrics.baseline || {};
    const optimized = metrics.optimized || {};
    setText('baseline-distance', baseline.distance_km, ' km');
    setText('baseline-time', baseline.time_min, ' min');
    setText('baseline-exposure', baseline.avg_exposure);
    setText('optimized-distance', optimized.distance_km, ' km');
    setText('optimized-time', optimized.time_min, ' min');
    setText('optimized-exposure', optimized.avg_exposure);
}

export function renderMeta(meta) {
    const status = document.getElementById('data-status');
    if (!status) return;

    const source = meta.source === 'cache' ? 'CACHED' : String(meta.source || 'UNKNOWN').toUpperCase();
    const details = [source];
    if (meta.scenario_title) details.push(meta.scenario_title);
    if (meta.event_count != null) details.push(`${meta.event_count} weather events`);
    if (meta.fetched_at) details.push(`fetched ${meta.fetched_at}`);
    if (meta.vertical_exaggeration != null) details.push(`vertical scale x${meta.vertical_exaggeration}`);
    if (meta.trajectory_status) details.push(meta.trajectory_status);
    status.textContent = details.join(' | ');
}

export function renderAltitudeLegend(grid) {
    const list = document.getElementById('altitude-level-list');
    if (!list) return;
    list.replaceChildren();

    const levels = new Map();
    grid.forEach(point => {
        Object.entries(point.levels || {}).forEach(([pressure, data]) => {
            if (!data || !Number.isFinite(data.y) || !Number.isFinite(data.altitude_km)) return;
            if (!levels.has(pressure)) levels.set(pressure, { heights: [], altitudes: [] });
            levels.get(pressure).heights.push(data.y);
            levels.get(pressure).altitudes.push(data.altitude_km);
        });
    });

    [...levels.entries()]
    .map(([pressure, data]) => ({
            pressure,
            height: median(data.heights),
            altitude: median(data.altitudes),
        }))
        .sort((left, right) => left.height - right.height)
        .forEach((level, index) => {
            const row = document.createElement('div');
            row.className = 'altitude-level-row';

            const swatch = document.createElement('span');
            swatch.className = 'altitude-level-swatch';
            swatch.style.backgroundColor = `#${PRESSURE_LEVEL_COLORS[index % PRESSURE_LEVEL_COLORS.length].toString(16).padStart(6, '0')}`;

            const pressure = document.createElement('strong');
            pressure.textContent = `${level.pressure} hPa`;

            const altitude = document.createElement('span');
            altitude.textContent = `${level.altitude.toFixed(1)} km`;

            row.append(swatch, pressure, altitude);
            list.append(row);
        });
}

function renderGrid(grid, group) {
    const width = coordinateStep(grid, 'x');
    const depth = coordinateStep(grid, 'z');
    if (width === null || depth === null) return;

    const geometry = new THREE.PlaneGeometry(width, depth);
    geometry.rotateX(-Math.PI / 2);
    const cellsByColor = new Map();

    grid.forEach(point => {
        if (!Number.isFinite(point.x) || !Number.isFinite(point.z)) return;

        Object.values(point.levels || {}).forEach(level => {
            if (!level || !Number.isFinite(level.y)) return;
            const color = scoreToColor(level.exposure_score);
            if (!cellsByColor.has(color)) cellsByColor.set(color, []);
            cellsByColor.get(color).push([point.x, level.y, point.z]);
        });
    });

    cellsByColor.forEach((positions, color) => {
        const material = new THREE.MeshBasicMaterial({
            color,
            transparent: true,
            opacity: 0.45,
            side: THREE.DoubleSide,
        });
        const cells = new THREE.InstancedMesh(geometry, material, positions.length);
        const transform = new THREE.Object3D();

        positions.forEach(([x, y, z], index) => {
            transform.position.set(x, y, z);
            transform.updateMatrix();
            cells.setMatrixAt(index, transform.matrix);
        });

        cells.instanceMatrix.needsUpdate = true;
        group.add(cells);
    });
}

function renderAltitudeLayers(grid, group) {
    const levels = new Map();
    const xValues = [];
    const zValues = [];

    grid.forEach(point => {
        if (Number.isFinite(point.x)) xValues.push(point.x);
        if (Number.isFinite(point.z)) zValues.push(point.z);
        Object.entries(point.levels || {}).forEach(([pressure, data]) => {
            if (!data || !Number.isFinite(data.y)) return;
            if (!levels.has(pressure)) levels.set(pressure, { heights: [], altitudes: [] });
            const level = levels.get(pressure);
            level.heights.push(data.y);
            if (Number.isFinite(data.altitude_km)) level.altitudes.push(data.altitude_km);
        });
    });

    if (!xValues.length || !zValues.length) return;
    const minX = Math.min(...xValues);
    const maxX = Math.max(...xValues);
    const minZ = Math.min(...zValues);
    const maxZ = Math.max(...zValues);
    const orderedLevels = [...levels.entries()].sort(
        (left, right) => median(left[1].heights) - median(right[1].heights),
    );

    orderedLevels.forEach(([pressure, data], index) => {
        const color = PRESSURE_LEVEL_COLORS[index % PRESSURE_LEVEL_COLORS.length];
        const y = median(data.heights);
        const outlineGeometry = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(minX, y, minZ),
            new THREE.Vector3(maxX, y, minZ),
            new THREE.Vector3(maxX, y, maxZ),
            new THREE.Vector3(minX, y, maxZ),
        ]);
        const outlineMaterial = new THREE.LineBasicMaterial({
            color,
            transparent: true,
            opacity: 0.6,
            depthTest: false,
        });
        const outline = new THREE.LineLoop(outlineGeometry, outlineMaterial);
        outline.renderOrder = 2;
        group.add(outline);

        const altitude = median(data.altitudes);
        if (Number.isFinite(altitude)) {
            const label = createAltitudeLabel(`${pressure} hPa  |  ${altitude.toFixed(1)} km`, color);
            label.position.set(minX + 26 + index * 78, y, minZ + 18);
            group.add(label);
        }
    });
}

function createAltitudeLabel(text, color) {
    const canvas = document.createElement('canvas');
    canvas.width = 384;
    canvas.height = 84;
    const context = canvas.getContext('2d');
    context.fillStyle = 'rgba(10, 18, 24, 0.9)';
    context.fillRect(2, 2, canvas.width - 4, canvas.height - 4);
    context.strokeStyle = `#${color.toString(16).padStart(6, '0')}`;
    context.lineWidth = 5;
    context.strokeRect(2, 2, canvas.width - 4, canvas.height - 4);
    context.fillStyle = '#f1f5f6';
    context.font = 'bold 28px sans-serif';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(text, canvas.width / 2, canvas.height / 2);

    const texture = new THREE.CanvasTexture(canvas);
    const material = new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        depthTest: false,
        depthWrite: false,
    });
    const label = new THREE.Sprite(material);
    label.scale.set(72, 16, 1);
    label.renderOrder = 3;
    return label;
}

function collectMaterial(material, materials, textures) {
    materials.add(material);
    if (material.map) textures.add(material.map);
}

function median(values) {
    const sorted = [...values].sort((left, right) => left - right);
    if (!sorted.length) return NaN;
    return sorted[Math.floor(sorted.length / 2)];
}

function renderEvents(events, group) {
    const geometry = new THREE.SphereGeometry(2.2, 8, 8);
    const eventsByType = new Map();
    events.forEach(event => {
        if (!hasPosition(event.centroid)) return;
        if (!eventsByType.has(event.type)) eventsByType.set(event.type, []);
        eventsByType.get(event.type).push(event.centroid);
    });

    eventsByType.forEach((centroids, type) => {
        const material = new THREE.MeshBasicMaterial({
            color: EVENT_COLORS[type] || EVENT_COLORS.default,
        });
        const markers = new THREE.InstancedMesh(geometry, material, centroids.length);
        const transform = new THREE.Object3D();
        centroids.forEach((centroid, index) => {
            transform.position.set(centroid.x, centroid.y, centroid.z);
            transform.updateMatrix();
            markers.setMatrixAt(index, transform.matrix);
        });
        markers.instanceMatrix.needsUpdate = true;
        group.add(markers);
    });
}

function renderAirports(airports, group) {
    const geometry = new THREE.SphereGeometry(6, 12, 12);
    const material = new THREE.MeshBasicMaterial({ color: 0xffffff });

    airports.forEach(airport => {
        if (!hasPosition(airport)) return;
        const marker = new THREE.Mesh(geometry, material);
        marker.position.set(airport.x, airport.y, airport.z);
        marker.userData.isAirportMarker = true;
        marker.userData.markerRadius = 6;
        group.add(marker);
    });
}

function renderRoute(waypoints, color, style, group) {
    if (!Array.isArray(waypoints) || waypoints.length < 2 || !waypoints.every(hasPosition)) return null;

    const curve = FlightCurve.fromPath({
        path: waypoints,
        color,
        style,
        taken: style === PathStyle.SOLID,
    });
    group.add(curve.createMesh());
    return curve;
}

function coordinateStep(points, axis) {
    const values = [...new Set(points.map(point => point[axis]).filter(Number.isFinite))].sort((a, b) => a - b);
    let step = Infinity;

    for (let index = 1; index < values.length; index += 1) {
        const difference = values[index] - values[index - 1];
        if (difference > 0) step = Math.min(step, difference);
    }

    return Number.isFinite(step) ? step : null;
}

function scoreToColor(score) {
    if (!Number.isFinite(score)) return EXPOSURE_COLORS.unknown;
    if (score <= 25) return EXPOSURE_COLORS.low;
    if (score <= 50) return EXPOSURE_COLORS.moderate;
    if (score <= 75) return EXPOSURE_COLORS.elevated;
    return EXPOSURE_COLORS.high;
}

function hasPosition(point) {
    return point && Number.isFinite(point.x) && Number.isFinite(point.y) && Number.isFinite(point.z);
}