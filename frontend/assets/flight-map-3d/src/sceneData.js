import * as THREE from 'three';

export function createLights(scene) {
    const ambient = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambient);

    const directional = new THREE.DirectionalLight(0xffffff, 1);
    directional.position.set(10, 20, 10);
    directional.castShadow = true;

    // Shadow camera bounds — how large an area can cast/receive shadows
    directional.shadow.camera.left = -20;
    directional.shadow.camera.right = 20;
    directional.shadow.camera.top = 20;
    directional.shadow.camera.bottom = -20;

    scene.add(directional);
}xport function createSceneDataGroup(payload) {
    const group = new THREE.Group();
    renderGrid(payload.grid || [], group);
    renderEvents(payload.events || [], group);
    renderAirports(payload.airports || [], group);

    const routes = payload.routes || {};
    renderRoute(routes.baseline, 0x3399ff, group);
    renderRoute(routes.optimized, 0xff6633, group);
    return group;
}

export function disposeSceneDataGroup(group) {
    const geometries = new Set();
    const materials = new Set();

    group.traverse(object => {
        if (object.geometry) geometries.add(object.geometry);
        if (Array.isArray(object.material)) {
            object.material.forEach(material => materials.add(material));
        } else if (object.material) {
            materials.add(object.material);
        }
    });

    geometries.forEach(geometry => geometry.dispose());
    materials.forEach(material => material.dispose());
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
    if (meta.fetched_at) details.push(`fetched ${meta.fetched_at}`);
    if (meta.vertical_exaggeration != null) details.push(`vertical scale x${meta.vertical_exaggeration}`);
    if (meta.trajectory_status) details.push(meta.trajectory_status);
    status.textContent = details.join(' | ');
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

function renderEvents(events, group) {
    const geometry = new THREE.SphereGeometry(4, 8, 8);

    events.forEach(event => {
        const centroid = event.centroid;
        if (!hasPosition(centroid)) return;
        const material = new THREE.MeshBasicMaterial({
            color: EVENT_COLORS[event.type] || EVENT_COLORS.default,
        });
        const marker = new THREE.Mesh(geometry, material);
        marker.position.set(centroid.x, centroid.y, centroid.z);
        group.add(marker);
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

function renderRoute(waypoints, color, group) {
    if (!Array.isArray(waypoints) || waypoints.length < 2 || !waypoints.every(hasPosition)) return;

    const points = waypoints.map(waypoint => new THREE.Vector3(waypoint.x, waypoint.y, waypoint.z));
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({ color });
    group.add(new THREE.Line(geometry, material));
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