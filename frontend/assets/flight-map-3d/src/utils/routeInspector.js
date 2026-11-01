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

const PANEL_STYLES = `
.airspace-inspect-panel {
    position: fixed;
    z-index: 9999;
    min-width: 258px;
    max-width: 320px;
    padding: 14px 16px 12px;
    background: rgba(12, 19, 29, 0.9);
    border: 1px solid rgba(227, 181, 99, 0.4);
    border-radius: 12px;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.55), inset 0 1px 0 rgba(255,255,255,0.05);
    backdrop-filter: blur(14px) saturate(1.2);
    color: #e9eef4;
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 12px;
    line-height: 1.5;
    font-feature-settings: 'tnum' 1;
    pointer-events: auto;
    animation: airspace-panel-in 0.16s ease-out;
}
@keyframes airspace-panel-in {
    from { opacity: 0; transform: translateY(6px) scale(0.97); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
}
.airspace-inspect-panel .route-chip {
    display: inline-block;
    padding: 3px 11px;
    margin-bottom: 9px;
    border-radius: 999px;
    font-weight: 700;
    font-size: 10px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #0a0f16;
}
.airspace-inspect-panel .section {
    margin-top: 9px;
    padding-top: 7px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.airspace-inspect-panel .section-title {
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: #5c7086;
    margin-bottom: 3px;
}
.airspace-inspect-panel .row {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 1.5px 0;
}
.airspace-inspect-panel .row .key { color: #8fa3b5; }
.airspace-inspect-panel .row .val { color: #eef3f8; font-weight: 600; }
.airspace-inspect-panel .close {
    position: absolute;
    top: 8px;
    right: 10px;
    width: 18px;
    height: 18px;
    border: none;
    background: transparent;
    color: #5c7086;
    font-size: 14px;
    line-height: 18px;
    cursor: pointer;
    padding: 0;
}
.airspace-inspect-panel .close:hover { color: #e3b563; }
`;

/**
 * Click-to-inspect for flight routes. Click (not drag) any rendered route to
 * get its exact geographic coordinates, the aircraft's modeled state at that
 * point (fuel, phase), and the nearest weather cell's forecast values —
 * shown in an on-screen panel AND reported to Flutter through
 * flutter_inappwebview.callHandler plus window.postMessage.
 */
export function createRouteInspector({ camera, domElement, getDataGroup, getPayload, scene }) {
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let downX = 0;
    let downY = 0;
    let downTime = 0;
    let marker = null;
    let markerTime = 0;
    let panel = null;
    const listeners = [];

    ensureStyles();
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
            hidePanel();
            emit({ type: 'airspace:route-point-cleared' });
            return;
        }

        const root = labeledRootOf(hits[0].object);
        if (!root) return;
        const point = hits[0].point;
        const payload = describePoint(root, point);
        placeMarker(point, root.userData.routeColor || 0x4dd8ff);
        showPanel(payload, event.clientX, event.clientY);
        emit({ type: 'airspace:route-point', ...payload });
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
            altitude_km: Number(geo.altitude_km.toFixed(2)),
            x: Number(point.x.toFixed(2)),
            y: Number(point.y.toFixed(2)),
            z: Number(point.z.toFixed(2)),
            route_progress: progress != null ? Number(progress.toFixed(4)) : null,
            pressure_level: nearestWaypoint ? nearestWaypoint.pressure_level ?? null : null,
            exposure_score: nearestWaypoint ? nearestWaypoint.exposure_score ?? null : null,
            waypoint_index: nearestIndex,
            phase,
            fuel_remaining_kg: fuel != null ? Math.round(fuel) : null,
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
    // --- On-screen panel ---------------------------------------------------

    function ensureStyles() {
        if (document.getElementById('airspace-inspect-styles')) return;
        const style = document.createElement('style');
        style.id = 'airspace-inspect-styles';
        style.textContent = PANEL_STYLES;
        document.head.appendChild(style);
    }

    function ensurePanel() {
        if (panel) return panel;
        panel = document.createElement('div');
        panel.className = 'airspace-inspect-panel';
        panel.style.display = 'none';
        document.body.appendChild(panel);
        return panel;
    }

    function showPanel(payload, clickX, clickY) {
        const element = ensurePanel();

        const colorHex = `#${(payload.route === 'optimized' ? 0xe3b563
            : payload.route === 'baseline' ? 0x5f7f9b : 0x8a97a5)
            .toString(16).padStart(6, '0')}`;

        const row = (key, value) =>
            `<div class="row"><span class="key">${key}</span><span class="val">${value}</span></div>`;
        const fmt = (value, suffix = '') => (value == null ? '—' : `${value}${suffix}`);

        const w = payload.weather || {};
        element.innerHTML = `
            <button class="close" title="Close">×</button>
            <span class="route-chip" style="background:${colorHex}">${payload.route}</span>
            ${row('Phase', fmt(payload.phase ? payload.phase.toUpperCase() : null))}
            ${row('Latitude', `${payload.lat.toFixed(4)}°`)}
            ${row('Longitude', `${payload.lon.toFixed(4)}°`)}
            ${row('Altitude', `${payload.altitude_km.toFixed(2)} km`)}
            ${row('Progress', payload.route_progress != null ? `${(payload.route_progress * 100).toFixed(1)}%` : '—')}
            ${row('Level', payload.pressure_level != null ? `${payload.pressure_level} hPa` : '—')}
            ${row('Exposure', fmt(payload.exposure_score, ' / 100'))}
            ${payload.fuel_remaining_kg != null ? `
            <div class="section">
                <div class="section-title">Aircraft</div>
                ${row('Fuel remaining', `${payload.fuel_remaining_kg.toLocaleString()} kg`)}
            </div>` : ''}
            <div class="section">
                <div class="section-title">Nearest forecast cell</div>
                ${row('Temperature', w.temperature != null ? `${w.temperature} °C` : '—')}
                ${row('Wind', w.wind_speed != null ? `${w.wind_speed} km/h ${w.wind_direction != null ? `@ ${w.wind_direction}°` : ''}` : '—')}
                ${row('Humidity', w.relative_humidity != null ? `${w.relative_humidity} %` : '—')}
                ${row('Cloud cover', w.cloud_cover != null ? `${w.cloud_cover} %` : '—')}
                ${row('Precipitation', w.precipitation != null ? `${w.precipitation} mm` : '—')}
                ${row('CAPE', w.cape != null ? `${w.cape} J/kg` : '—')}
            </div>
        `;

        element.querySelector('.close').addEventListener('click', () => {
            hidePanel();
            clearMarker();
        });

        // Position near the click, clamped inside the viewport.
        element.style.display = 'block';
        const panelRect = element.getBoundingClientRect();
        const left = Math.min(Math.max(12, clickX + 16), window.innerWidth - panelRect.width - 12);
        const top = Math.min(Math.max(12, clickY - panelRect.height - 16), window.innerHeight - panelRect.height - 12);
        element.style.left = `${left}px`;
        element.style.top = `${top}px`;
    }

    function hidePanel() {
        if (panel) panel.style.display = 'none';
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

    // --- Flutter bridge ----------------------------------------------------

    function emit(payload) {
        try {
            if (window.flutter_inappwebview && window.flutter_inappwebview.callHandler) {
                window.flutter_inappwebview.callHandler(
                    payload.type === 'airspace:route-point' ? 'onRoutePointSelected' : 'onRoutePointCleared',
                    payload,
                );
            }
        } catch (error) {
            console.warn('routeInspector: Flutter handler unavailable', error);
        }
        try {
            window.postMessage(payload, '*');
            if (window.parent && window.parent !== window) window.parent.postMessage(payload, '*');
        } catch (error) {
            console.warn('routeInspector: postMessage failed', error);
        }
        listeners.forEach(listener => listener(payload));
    }

    return {
        onPick(listener) {
            listeners.push(listener);
            return () => {
                const index = listeners.indexOf(listener);
                if (index >= 0) listeners.splice(index, 1);
            };
        },

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
            hidePanel();
        },
    };
}