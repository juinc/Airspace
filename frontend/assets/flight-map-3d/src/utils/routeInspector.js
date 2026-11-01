import * as THREE from 'three';

// Must mirror grid/coordinates.py exactly — the backend bakes every scene y
// with VERTICAL_EXAGGERATION = 4. Dividing by anything else misreports
// altitude in the inspector panel.
const GRID_ORIGIN_LAT = 45.625;
const GRID_ORIGIN_LON = 24.875;
const EARTH_M_PER_DEG_LAT = 111320;
const VERTICAL_EXAGGERATION = 4;

export function sceneToGeo(point) {
    const metersPerDegLon = EARTH_M_PER_DEG_LAT * Math.cos((GRID_ORIGIN_LAT * Math.PI) / 180);
    return {
        lat: GRID_ORIGIN_LAT + (point.z * 1000) / EARTH_M_PER_DEG_LAT,
        lon: GRID_ORIGIN_LON + (point.x * 1000) / metersPerDegLon,
        altitude_km: point.y / VERTICAL_EXAGGERATION,
    };
}

const PICK_DRAG_THRESHOLD_PX = 6;
const CURVE_SAMPLES = 240;

/**
 * Click-to-inspect for flight routes. Click (not drag) any rendered route to
 * get geographic coordinates, route state, and the nearest forecast values.
 * Flutter owns the display; this module only reports the selected scene point.
 */
export function createRouteInspector({
    camera,
    domElement,
    getDataGroup,
    getPayload,
    scene,
    onSelection,
    onClear,
}) {
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let downX = 0;
    let downY = 0;
    let downTime = 0;
    let marker = null;
    let markerTime = 0;
    domElement.addEventListener('pointerdown', event => {
        downX = event.clientX;
        downY = event.clientY;
        downTime = performance.now();
    });

    domElement.addEventListener('pointerup', event => {
        const moved = Math.hypot(event.clientX - downX, event.clientY - downY);
        if (moved > PICK_DRAG_THRESHOLD_PX || performance.now() - downTime > 600) return;
        handlePick(event);
    });

    function findRouteRoots(group) {
        const roots = [];
        if (!group) return roots;
        group.traverse(object => {
            if (object.userData && object.userData.routeLabel) roots.push(object);
        });
        return roots;
    }

    function labeledRootOf(object) {
        let current = object;
        while (current) {
            if (current.userData && current.userData.routeLabel) return current;
            current = current.parent;
        }
        return null;
    }

    function handlePick(event) {
        const group = getDataGroup();
        const roots = findRouteRoots(group);
        if (roots.length === 0) return;

        const rect = domElement.getBoundingClientRect();
        pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(pointer, camera);

        const hits = raycaster.intersectObjects(roots, true);
        if (hits.length === 0) {
            clearMarker();
            onClear?.();
            return;
        }

        const root = labeledRootOf(hits[0].object);
        if (!root) return;
        const point = hits[0].point;
        const payload = describePoint(root, point);
        placeMarker(point, root.userData.routeColor || 0x4dd8ff);
        onSelection?.(payload);
    }

    function describePoint(root, point) {
        const geo = sceneToGeo(point);
        const label = root.userData.routeLabel;
        const curve = root.userData.flightCurve && root.userData.flightCurve.curve;
        const waypoints = root.userData.routeWaypoints || [];
        const payload = getPayload ? getPayload() : null;

        let progress = null;
        if (curve) {
            // Cache the arc-length-spaced samples on the route root: the
            // route doesn't change between clicks, so we compute the
            // expensive spacing ONCE instead of 241 getPointAt calls per click.
            let samples = root.userData.spacedPoints;
            if (!samples || samples.length !== CURVE_SAMPLES + 1) {
                samples = curve.getSpacedPoints(CURVE_SAMPLES);
                root.userData.spacedPoints = samples;
            }
            let bestDistance = Infinity;
            let bestT = 0;
            for (let i = 0; i <= CURVE_SAMPLES; i++) {
                const distance = samples[i].distanceToSquared(point);
                if (distance < bestDistance) {
                    bestDistance = distance;
                    bestT = i / CURVE_SAMPLES;
                }
            }
            progress = bestT;
        }

        // Nearest raw waypoint carries exposure / phase / timing info.
        let nearestWaypoint = null;
        let nearestIndex = null;
        let bestWaypointDistance = Infinity;
        waypoints.forEach((waypoint, index) => {
            const distance = (waypoint.x - point.x) ** 2 + (waypoint.z - point.z) ** 2;
            if (distance < bestWaypointDistance) {
                bestWaypointDistance = distance;
                nearestWaypoint = waypoint;
                nearestIndex = index;
            }
        });

        // Aircraft state at this point: fuel from the route's own timing.
        let fuel = null;
        let phase = nearestWaypoint ? nearestWaypoint.phase ?? null : null;
        if (payload && label === 'optimized') {
            const metrics = (payload.routes && payload.routes.metrics && payload.routes.metrics.optimized) || {};
            if (metrics.initial_fuel_kg != null && nearestWaypoint) {
                const cumulative = nearestWaypoint.cumulative_time_min;
                if (cumulative != null && metrics.time_min) {
                    const burnPerMin = metrics.fuel_estimated_kg / metrics.time_min;
                    fuel = Math.max(0, metrics.initial_fuel_kg - burnPerMin * cumulative);
                } else if (progress != null) {
                    fuel = Math.max(0, metrics.initial_fuel_kg - (metrics.fuel_estimated_kg || 0) * progress);
                }
            }
        }

        // Weather at the nearest grid cell, closest pressure level by altitude.
        const weather = payload ? nearestCellWeather(payload.grid || [], geo) : null;

        return {
            route: label,
            lat: Number(geo.lat.toFixed(5)),
            lon: Number(geo.lon.toFixed(5)),
            altitudeKm: Number(geo.altitude_km.toFixed(2)),
            x: Number(point.x.toFixed(2)),
            y: Number(point.y.toFixed(2)),
            z: Number(point.z.toFixed(2)),
            routeProgress: progress != null ? Number(progress.toFixed(4)) : null,
            pressureLevel: nearestWaypoint ? nearestWaypoint.pressure_level ?? null : null,
            exposureScore: nearestWaypoint ? nearestWaypoint.exposure_score ?? null : null,
            waypointIndex: nearestIndex,
            phase,
            fuelRemainingKg: fuel != null ? Math.round(fuel) : null,
            weather,
        };
    }

    function nearestCellWeather(grid, geo) {
        if (!grid.length) return null;

        // Nearest horizontal grid cell by scene-space distance. The click's
        // lat/lon maps back to scene x/z via the same origin constants.
        const metersPerDegLon = EARTH_M_PER_DEG_LAT * Math.cos((GRID_ORIGIN_LAT * Math.PI) / 180);
        const clickX = (geo.lon - GRID_ORIGIN_LON) * metersPerDegLon / 1000;
        const clickZ = (geo.lat - GRID_ORIGIN_LAT) * EARTH_M_PER_DEG_LAT / 1000;

        let cell = null;
        let bestDistance = Infinity;
        for (const candidate of grid) {
            if (candidate.x == null || candidate.z == null) continue;
            const d = (candidate.x - clickX) ** 2 + (candidate.z - clickZ) ** 2;
            if (d < bestDistance) {
                bestDistance = d;
                cell = candidate;
            }
        }
        if (!cell) return null;

        // Closest pressure level to the clicked altitude.
        let levelData = null;
        let bestAltitude = Infinity;
        for (const data of Object.values(cell.levels || {})) {
            if (!data || data.altitude_km == null) continue;
            const d = Math.abs(data.altitude_km - geo.altitude_km);
            if (d < bestAltitude) {
                bestAltitude = d;
                levelData = data;
            }
        }

        return {
            temperature: levelData ? levelData.temperature ?? null : null,
            wind_speed: levelData ? levelData.wind_speed ?? null : null,
            wind_direction: levelData ? levelData.wind_direction ?? null : null,
            relative_humidity: levelData ? levelData.relative_humidity ?? null : null,
            cloud_cover: cell.cloud_cover ?? null,
            precipitation: cell.precipitation ?? null,
            cape: cell.cape ?? null,
        };
    }
    // --- Scene marker ------------------------------------------------------

    function placeMarker(point, color) {
        clearMarker();
        marker = new THREE.Group();

        const core = new THREE.Mesh(
            new THREE.SphereGeometry(4, 16, 16),
            new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false }),
        );
        core.renderOrder = 20;

        const halo = new THREE.Mesh(
            new THREE.RingGeometry(7, 9, 32),
            new THREE.MeshBasicMaterial({
                color,
                transparent: true,
                opacity: 0.9,
                side: THREE.DoubleSide,
                depthWrite: false,
                depthTest: false,
            }),
        );
        halo.renderOrder = 20;

        marker.add(core, halo);
        marker.position.copy(point);
        marker.userData.halo = halo;
        scene.add(marker);
    }

    function clearMarker() {
        if (!marker) return;
        scene.remove(marker);
        marker.traverse(object => {
            if (object.geometry) object.geometry.dispose();
            if (object.material) object.material.dispose();
        });
        marker = null;
    }

    return {
        update(delta) {
            if (!marker) return;
            markerTime += delta;
            const halo = marker.userData.halo;
            const pulse = 1 + 0.35 * (0.5 + 0.5 * Math.sin(markerTime * 4));
            halo.scale.setScalar(pulse);
            halo.material.opacity = 0.9 - 0.5 * (0.5 + 0.5 * Math.sin(markerTime * 4));
        },

        clear() {
            clearMarker();
            onClear?.();
        },
    };
}