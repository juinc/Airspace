import * as THREE from 'three';
import { FlightCurve, PathStyle } from './objects/flightCurve.js';
import { createContrail, createPlaneAnimator, instantiatePlane } from './objects/plane.js';
import { buildWeatherClusters } from './utils/weatherClusters.js';
import { createWeatherSpanMarkers } from './utils/weatherSpanMarkers.js';
import { pointsFromGrid } from './utils/weatherPointAdapters.js';

const PRESSURE_LEVEL_COLORS = [0x6fd3e8, 0x7fd6a4, 0xe3b563, 0xe2836f, 0xb48fe0];

// One distinct color per aircraft. Baselines stay uniform gray-dashed so
// the optimized paths (the stars of the show) always dominate visually.
const FLIGHT_COLORS = [0xffb347, 0x6fd3e8, 0xb48fe0, 0x7fd6a4, 0xe2836f, 0xf0a35e];
const BASELINE_COLOR = 0x5f7f9b;
const PREVIOUS_COLOR = 0x7a8ea0;

// PERFORMANCE: hard cap on rendered cloud cells, kept sorted by severity so
// the worst weather always renders. 500 low-poly instances builds in well
// under one frame budget; the old 4500-instance build froze the tab.
const MAX_WEATHER_CELLS = 500;

const ENDPOINT_GROUND_OFFSET = 0.4;
const LOW_ALT_TERRAIN_CLEARANCE = 0.8;

// ---------------------------------------------------------------------------
// Scene data group
// ---------------------------------------------------------------------------

export function createSceneDataGroup(payload, planeTemplate, initialProgress = 0,
                                     weatherMeshKit = null, groundSampler = null) {
    const group = new THREE.Group();
    const updates = [];

    renderGrid(payload.grid || [], group, weatherMeshKit, updates);
    renderAltitudeLayers(payload.grid || [], group, updates);
    renderAirports(payload.airports || [], group, updates, groundSampler);

    const flights = normalizeFlights(payload);
    const planeStates = [];

    flights.forEach((flight, index) => {
        const color = FLIGHT_COLORS[index % FLIGHT_COLORS.length];

        const baselineMesh = renderRoute(flight.baseline, BASELINE_COLOR, PathStyle.DASHED, group, 'baseline', groundSampler);
        if (baselineMesh && baselineMesh.userData.update) updates.push(baselineMesh.userData.update);
        if (flight.previous_optimized) {
            renderRoute(flight.previous_optimized, PREVIOUS_COLOR, PathStyle.DASHED, group, 'previous_optimized', groundSampler);
        }
        const optimizedMesh = renderRoute(flight.optimized, color, PathStyle.SOLID, group, 'optimized', groundSampler);
        if (optimizedMesh && optimizedMesh.userData.update) updates.push(optimizedMesh.userData.update);

        if (optimizedMesh && planeTemplate) {
            const optimizedCurve = optimizedMesh.userData.flightCurve;
            const plane = instantiatePlane(planeTemplate);

            const planeBounds = new THREE.Box3().setFromObject(plane);
            const planeSize = planeBounds.getSize(new THREE.Vector3());
            const largestDimension = Math.max(planeSize.x, planeSize.y, planeSize.z);
            if (largestDimension > 0) plane.scale.multiplyScalar(26 / largestDimension);
            group.add(plane);

            const contrail = createContrail();
            group.add(contrail.line);

            // Stagger speeds so multiple aircraft never move in lockstep.
            const speed = 0.035 * (1 + index * 0.15);
            const updatePlane = createPlaneAnimator(
                plane,
                optimizedCurve.curve,
                speed,
                initialProgress,
                contrail,
            );
            updates.push(updatePlane);
            planeStates.push(updatePlane.getState);
        }
    });

    // HUD / progress read the lead aircraft; the full list is exposed too.
    group.userData.getFlightProgress = planeStates.length ? () => planeStates[0]().progress : null;
    group.userData.getPlaneState = planeStates.length ? planeStates[0] : null;
    group.userData.planeStates = planeStates;
    group.userData.flightCount = flights.length;

    group.userData.update = delta => updates.forEach(fn => fn(delta));
    return group;
}

function normalizeFlights(payload) {
    if (Array.isArray(payload.flights) && payload.flights.length) {
        return payload.flights.map((flight, index) => ({
            id: flight.id || `F${index + 1}`,
            baseline: flight.baseline,
            optimized: flight.optimized,
            previous_optimized: flight.previous_optimized,
        }));
    }
    const routes = payload.routes || {};
    return [{
        id: 'F1',
        baseline: routes.baseline,
        optimized: routes.optimized,
        previous_optimized: routes.previous_optimized,
    }];
}

// ---------------------------------------------------------------------------
// Disposal
// ---------------------------------------------------------------------------

export function disposeSceneDataGroup(group) {
    const geometries = new Set();
    const materials = new Set();
    const textures = new Set();

    group.traverse(object => {
        if (object.isInstancedMesh) object.dispose();

        if (object.geometry && !object.geometry.userData.shared) {
            geometries.add(object.geometry);
        }
        if (Array.isArray(object.material)) {
            object.material.forEach(material => {
                if (!material.userData.shared) collectMaterial(material, materials, textures);
            });
        } else if (object.material && !object.material.userData.shared) {
            collectMaterial(object.material, materials, textures);
        }
    });

    geometries.forEach(geometry => geometry.dispose());
    materials.forEach(material => material.dispose());
    textures.forEach(texture => {
        if (!texture.userData.shared) texture.dispose();
    });
}

// ---------------------------------------------------------------------------
// Airports / map alignment
// ---------------------------------------------------------------------------

export function alignAirportsToMap(group, mapMesh) {
    if (!mapMesh) return;

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

// ---------------------------------------------------------------------------
// DOM renderers
// ---------------------------------------------------------------------------

export function renderMetrics(metrics) {
    const setText = (id, value, suffix = '') => {
        const element = document.getElementById(id);
        if (element) element.textContent = `${value == null ? '—' : value}${suffix}`;
    };

    const baseline = metrics.baseline || {};
    const optimized = metrics.optimized || {};
    setText('baseline-distance', baseline.distance_km, ' km');
    setText('baseline-time', baseline.time_min, ' min');
    setText('baseline-exposure', baseline.avg_exposure);
    setText('optimized-distance', optimized.distance_km, ' km');
    setText('optimized-time', optimized.time_min, ' min');
    setText('optimized-exposure', optimized.avg_exposure);

    const deltaEl = document.getElementById('optimized-delta');
    if (deltaEl) {
        const parts = [];
        const fmt = (value, unit, round = false) => {
            if (value == null) return null;
            const shown = round ? Math.round(value).toLocaleString() : value.toFixed(1);
            return `${value > 0 ? '+' : ''}${shown} ${unit}`;
        };
        const dTime = optimized.time_min != null && baseline.time_min != null
            ? optimized.time_min - baseline.time_min : null;
        const dFuel = optimized.fuel_estimated_kg != null && baseline.fuel_estimated_kg != null
            ? optimized.fuel_estimated_kg - baseline.fuel_estimated_kg : null;
        const dExp = optimized.avg_exposure != null && baseline.avg_exposure != null
            ? optimized.avg_exposure - baseline.avg_exposure : null;
        const t = fmt(dTime, 'min');
        const f = fmt(dFuel, 'kg fuel', true);
        const e = fmt(dExp, 'exp');
        if (t) parts.push(t);
        if (f) parts.push(f);
        if (e) parts.push(e);
        deltaEl.textContent = parts.length ? `Δ ${parts.join(' · ')}` : '—';
        const better = (dTime ?? 0) <= 0 && (dExp ?? 0) <= 0;
        deltaEl.classList.toggle('delta-good', better && parts.length > 0);
        deltaEl.classList.toggle('delta-bad', !better && parts.length > 0);
    }
}

export function renderMeta(meta) {
    const status = document.getElementById('data-status');
    if (!status) return;

    const source = meta.source === 'cache' ? 'CACHED' : String(meta.source || 'UNKNOWN').toUpperCase();
    const details = [source];
    if (meta.scenario_title) details.push(meta.scenario_title);
    if (meta.event_count != null) details.push(`${meta.event_count} weather events`);
    if (meta.fetched_at) details.push(`fetched ${meta.fetched_at}`);
    if (meta.trajectory_status) details.push(meta.trajectory_status);
    status.textContent = details.join('  ·  ');
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
            const color = PRESSURE_LEVEL_COLORS[index % PRESSURE_LEVEL_COLORS.length];
            const row = document.createElement('div');
            row.className = 'altitude-level-row';

            const swatch = document.createElement('span');
            swatch.className = 'altitude-level-swatch';
            const hex = `#${color.toString(16).padStart(6, '0')}`;
            swatch.style.backgroundColor = hex;
            swatch.style.color = hex;

            const pressure = document.createElement('span');
            pressure.textContent = `${level.pressure} hPa`;

            const altitude = document.createElement('span');
            altitude.textContent = `${level.altitude.toFixed(1)} km`;

            row.append(swatch, pressure, altitude);
            list.append(row);
        });
}

// ---------------------------------------------------------------------------
// Weather grid — clouds only, capped instance count
// ---------------------------------------------------------------------------

function renderGrid(grid, group, weatherMeshKit, updates) {
    if (!weatherMeshKit) return;

    const allPoints = pointsFromGrid(grid);
    if (allPoints.length === 0) return;

    // Score every cell once; keep a Map so the cap can sort by severity.
    const withScores = new Map();
    allPoints.forEach(point => {
        const levelScores = Object.values(point.levels || {})
            .map(level => (level && Number.isFinite(level.exposure_score)) ? level.exposure_score : 0);
        const own = Number.isFinite(point.exposure_score) ? point.exposure_score : 0;
        withScores.set(point, Math.max(own, ...(levelScores.length ? levelScores : [0])));
    });

    const significant = allPoints.filter(point => withScores.get(point) >= 20);
    let points = significant.length >= 4 ? significant : allPoints;

    // PERFORMANCE: keep only the most severe cells when the field is huge.
    if (points.length > MAX_WEATHER_CELLS) {
        points = points
            .slice()
            .sort((a, b) => withScores.get(b) - withScores.get(a))
            .slice(0, MAX_WEATHER_CELLS);
    }

    const stepX = coordinateStep(points, 'x');
    const stepZ = coordinateStep(points, 'z');
    if (stepX === null || stepZ === null) return;
    const layerHeight = Math.min(20, Math.max(2,
        coordinateStep(points, 'y') || Math.min(stepX, stepZ)));

    const clusters = buildWeatherClusters(points, stepX, stepZ);
    if (clusters.length === 0) return;

    const markers = createWeatherSpanMarkers(clusters, weatherMeshKit, {
        cellStepX: stepX,
        cellStepZ: stepZ,
        layerHeight,
    });
    if (markers.userData.update) updates.push(markers.userData.update);
    group.add(markers);
}

// ---------------------------------------------------------------------------
// Altitude layers
// ---------------------------------------------------------------------------

function renderAltitudeLayers(grid, group, updates) {
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

    if (!xValues.length || !zValues.length || levels.size === 0) return;
    const minX = Math.min(...xValues);
    const maxX = Math.max(...xValues);
    const minZ = Math.min(...zValues);
    const maxZ = Math.max(...zValues);
    const orderedLevels = [...levels.entries()].sort(
        (left, right) => median(left[1].heights) - median(right[1].heights),
    );

    const bottomY = median(orderedLevels[0][1].heights);
    const topY = median(orderedLevels[orderedLevels.length - 1][1].heights);

    const pillarPoints = [];
    [[minX, minZ], [maxX, minZ], [maxX, maxZ], [minX, maxZ]].forEach(([x, z]) => {
        pillarPoints.push(new THREE.Vector3(x, bottomY, z), new THREE.Vector3(x, topY, z));
    });
    const pillarGeometry = new THREE.BufferGeometry().setFromPoints(pillarPoints);
    const pillarMaterial = new THREE.LineBasicMaterial({
        color: 0x2c4258,
        transparent: true,
        opacity: 0.35,
    });
    const pillars = new THREE.LineSegments(pillarGeometry, pillarMaterial);
    pillars.renderOrder = 2;
    group.add(pillars);

    let pillarTime = 0;
    updates.push(delta => {
        pillarTime += delta;
        pillarMaterial.opacity = 0.22 + 0.12 * (0.5 + 0.5 * Math.sin(pillarTime * 1.1));
    });

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
            opacity: 0.55,
            depthTest: false,
        });
        const outline = new THREE.LineLoop(outlineGeometry, outlineMaterial);
        outline.renderOrder = 2;
        group.add(outline);

        let t = index * 1.3;
        updates.push(delta => {
            t += delta;
            outlineMaterial.opacity = 0.35 + 0.22 * (0.5 + 0.5 * Math.sin(t * 1.4));
        });

        const altitude = median(data.altitudes);
        if (Number.isFinite(altitude)) {
            const label = createAltitudeLabel(`${pressure} hPa`, `${altitude.toFixed(1)} km`, color);
            label.position.set(minX + 26 + index * 78, y, minZ + 18);
            group.add(label);
        }
    });
}

function createAltitudeLabel(pressure, altitude, color) {
    const canvas = document.createElement('canvas');
    canvas.width = 320;
    canvas.height = 96;
    const context = canvas.getContext('2d');
    const hex = `#${color.toString(16).padStart(6, '0')}`;

    context.fillStyle = 'rgba(10, 16, 25, 0.88)';
    roundedRectPath(context, 4, 14, 312, 68, 34);
    context.fill();
    context.strokeStyle = 'rgba(255, 255, 255, 0.14)';
    context.lineWidth = 2;
    roundedRectPath(context, 4, 14, 312, 68, 34);
    context.stroke();

    context.fillStyle = hex;
    context.beginPath();
    context.arc(38, 48, 7, 0, Math.PI * 2);
    context.fill();

    context.fillStyle = '#eef3f8';
    context.font = '600 26px Inter, sans-serif';
    context.textAlign = 'left';
    context.textBaseline = 'middle';
    context.fillText(pressure, 58, 42);

    context.fillStyle = '#8fa3b5';
    context.font = '400 21px Inter, sans-serif';
    context.fillText(`${altitude} km`, 58, 68);

    const texture = new THREE.CanvasTexture(canvas);
    const material = new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        depthTest: false,
        depthWrite: false,
    });
    const label = new THREE.Sprite(material);
    label.scale.set(64, 19, 1);
    label.renderOrder = 3;
    return label;
}

// ---------------------------------------------------------------------------
// Airports — gold executive markers
// ---------------------------------------------------------------------------

let beamTextureCache = null;
function beamTexture() {
    if (beamTextureCache) return beamTextureCache;
    const canvas = document.createElement('canvas');
    canvas.width = 4;
    canvas.height = 128;
    const context = canvas.getContext('2d');
    const gradient = context.createLinearGradient(0, 0, 0, 128);
    gradient.addColorStop(0, 'rgba(255,255,255,0)');
    gradient.addColorStop(0.35, 'rgba(255,255,255,0.35)');
    gradient.addColorStop(1, 'rgba(255,255,255,0.9)');
    context.fillStyle = gradient;
    context.fillRect(0, 0, 4, 128);
    const texture = new THREE.CanvasTexture(canvas);
    texture.userData.shared = true;
    beamTextureCache = texture;
    return texture;
}

let groundGlowTextureCache = null;
function groundGlowTexture() {
    if (groundGlowTextureCache) return groundGlowTextureCache;
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 128;
    const context = canvas.getContext('2d');
    const gradient = context.createRadialGradient(64, 64, 4, 64, 64, 64);
    gradient.addColorStop(0, 'rgba(255,255,255,1)');
    gradient.addColorStop(0.4, 'rgba(255,255,255,0.35)');
    gradient.addColorStop(1, 'rgba(255,255,255,0)');
    context.fillStyle = gradient;
    context.fillRect(0, 0, 128, 128);
    const texture = new THREE.CanvasTexture(canvas);
    texture.userData.shared = true;
    groundGlowTextureCache = texture;
    return texture;
}

function renderAirports(airports, group, updates, groundSampler) {
    if (!Array.isArray(airports) || airports.length === 0) return;

    const coreGeometry = new THREE.SphereGeometry(6, 16, 16);
    const coreMaterial = new THREE.MeshBasicMaterial({ color: 0xf5ead2 });
    const ringGeometry = new THREE.RingGeometry(8, 10, 32);
    const beamGeometry = new THREE.CylinderGeometry(2.5, 5, 130, 12, 1, true);
    beamGeometry.translate(0, 65, 0);
    const discGeometry = new THREE.CircleGeometry(18, 32);

    airports.forEach((airport, index) => {
        if (!hasPosition(airport)) return;

        const marker = new THREE.Mesh(coreGeometry, coreMaterial);
        marker.position.set(airport.x, airport.y, airport.z);
        marker.userData.isAirportMarker = true;
        marker.userData.markerRadius = 6;
        if (groundSampler) {
            const groundY = groundSampler(airport.x, airport.z);
            if (groundY != null) marker.position.y = groundY + marker.userData.markerRadius;
        }
        group.add(marker);

        const ringMaterial = new THREE.MeshBasicMaterial({
            color: 0xe3b563,
            transparent: true,
            opacity: 0.7,
            side: THREE.DoubleSide,
            depthWrite: false,
        });
        const ring = new THREE.Mesh(ringGeometry, ringMaterial);
        ring.rotation.x = -Math.PI / 2;
        ring.position.copy(marker.position);
        ring.renderOrder = 5;
        group.add(ring);

        const beamMaterial = new THREE.MeshBasicMaterial({
            map: beamTexture(),
            color: 0x9adcf0,
            transparent: true,
            opacity: 0.3,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
            side: THREE.DoubleSide,
        });
        const beam = new THREE.Mesh(beamGeometry, beamMaterial);
        beam.position.copy(marker.position);
        beam.renderOrder = 1;
        group.add(beam);

        const discMaterial = new THREE.MeshBasicMaterial({
            map: groundGlowTexture(),
            color: 0x8a6a35,
            transparent: true,
            opacity: 0.4,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        });
        const disc = new THREE.Mesh(discGeometry, discMaterial);
        disc.rotation.x = -Math.PI / 2;
        disc.renderOrder = 0;
        group.add(disc);

        const code = airport.code || airport.name;
        const label = code ? createAirportLabel(String(code)) : null;
        if (label) group.add(label);

        let phase = (airport.x % 10) / 10;
        let time = 0;
        const updateAirport = delta => {
            time += delta;
            phase = (phase + delta * 0.8) % 1;
            ring.scale.setScalar(1 + phase * 2.5);
            ring.position.set(marker.position.x, marker.position.y + phase * 14, marker.position.z);
            ringMaterial.opacity = 0.7 * (1 - phase);

            const breathe = 0.5 + 0.5 * Math.sin(time * 1.6 + index * 2.1);
            beamMaterial.opacity = 0.2 + 0.14 * breathe;
            beam.position.copy(marker.position);
            disc.position.set(marker.position.x, marker.position.y + 0.6, marker.position.z);
            discMaterial.opacity = 0.28 + 0.18 * breathe;
            if (label) label.position.set(marker.position.x, marker.position.y + 34, marker.position.z);
        };
        updates.push(updateAirport);
    });
}

function createAirportLabel(text) {
    const match = text.match(/^(\S+)\s+(.+)$/);
    const code = match ? match[1] : text;
    const city = match ? match[2] : '';

    const canvas = document.createElement('canvas');
    canvas.width = 320;
    canvas.height = 120;
    const context = canvas.getContext('2d');

    context.fillStyle = 'rgba(9, 14, 22, 0.88)';
    roundedRectPath(context, 8, 18, 304, 84, 26);
    context.fill();
    context.strokeStyle = 'rgba(227, 181, 99, 0.55)';
    context.lineWidth = 2;
    roundedRectPath(context, 8, 18, 304, 84, 26);
    context.stroke();

    context.fillStyle = '#e3b563';
    context.font = '700 34px Inter, sans-serif';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(code, canvas.width / 2, 52);

    if (city) {
        context.fillStyle = '#a9bdca';
        context.font = '400 22px Inter, sans-serif';
        context.fillText(city.toUpperCase(), canvas.width / 2, 82);
    }

    const texture = new THREE.CanvasTexture(canvas);
    const material = new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        depthTest: false,
        depthWrite: false,
    });
    const label = new THREE.Sprite(material);
    label.scale.set(46, 17, 1);
    label.renderOrder = 6;
    return label;
}

// ---------------------------------------------------------------------------
// Routes — raw backend paths, terrain-snapped, tagged for the inspector
// ---------------------------------------------------------------------------

function renderRoute(waypoints, color, style, group, label = 'route', groundSampler = null) {
    if (!Array.isArray(waypoints) || waypoints.length < 2 || !waypoints.every(hasPosition)) return null;

    const path = waypoints.map(waypoint => ({ ...waypoint }));

    if (groundSampler) {
        path.forEach((waypoint, index) => {
            const groundY = groundSampler(waypoint.x, waypoint.z);
            if (groundY == null) return;
            const isEndpoint = index === 0 || index === path.length - 1;
            if (isEndpoint) {
                waypoint.y = groundY + ENDPOINT_GROUND_OFFSET;
            } else if (waypoint.altitude_km != null && waypoint.altitude_km < 2.5) {
                waypoint.y = Math.max(waypoint.y, groundY + LOW_ALT_TERRAIN_CLEARANCE);
            }
        });
    }

    const curve = FlightCurve.fromPath({
        path,
        color,
        style,
    });
    const mesh = curve.createMesh();
    mesh.userData.flightCurve = curve;
    mesh.userData.routeLabel = label;
    mesh.userData.routeColor = color;
    mesh.userData.routeWaypoints = path;
    group.add(mesh);
    return mesh;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function roundedRectPath(context, x, y, width, height, radius) {
    context.beginPath();
    if (typeof context.roundRect === 'function') {
        context.roundRect(x, y, width, height, radius);
        return;
    }
    context.moveTo(x + radius, y);
    context.arcTo(x + width, y, x + width, y + height, radius);
    context.arcTo(x + width, y + height, x, y + height, radius);
    context.arcTo(x, y + height, x, y, radius);
    context.arcTo(x, y, x + width, y, radius);
    context.closePath();
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

function coordinateStep(points, axis) {
    const values = [...new Set(points.map(point => point[axis]).filter(Number.isFinite))].sort((a, b) => a - b);
    let step = Infinity;

    for (let index = 1; index < values.length; index += 1) {
        const difference = values[index] - values[index - 1];
        if (difference > 0) step = Math.min(step, difference);
    }

    return Number.isFinite(step) ? step : null;
}

function hasPosition(point) {
    return point && Number.isFinite(point.x) && Number.isFinite(point.y) && Number.isFinite(point.z);
}