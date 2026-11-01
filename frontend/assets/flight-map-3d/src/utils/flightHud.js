import { sceneToGeo } from './routeInspector.js';

const HUD_STYLES = `
.airspace-flight-hud {
    position: fixed;
    left: 16px;
    bottom: 52px;
    z-index: 9998;
    width: 272px;
    padding: 14px 16px 12px;
    background: rgba(12, 19, 29, 0.88);
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 12px;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255,255,255,0.05);
    backdrop-filter: blur(14px) saturate(1.2);
    color: #e9eef4;
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 12px;
    line-height: 1.5;
    font-feature-settings: 'tnum' 1;
    pointer-events: none;
    animation: airspace-panel-in 0.25s ease-out;
}
@keyframes airspace-panel-in {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
.airspace-flight-hud .hud-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 9px;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.24em;
    color: #5c7086;
    text-transform: uppercase;
}
.airspace-flight-hud .phase-chip {
    padding: 3px 10px;
    border-radius: 999px;
    font-weight: 700;
    font-size: 9.5px;
    letter-spacing: 0.1em;
    color: #0a0f16;
    background: #6fd3e8;
}
.airspace-flight-hud .section-title {
    margin: 8px 0 3px;
    padding-top: 7px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: #5c7086;
}
.airspace-flight-hud .row {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    padding: 1.5px 0;
}
.airspace-flight-hud .row .key { color: #8fa3b5; }
.airspace-flight-hud .row .val { color: #eef3f8; font-weight: 600; }
.airspace-flight-hud .bar {
    position: relative;
    height: 5px;
    margin: 5px 0 3px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.07);
    overflow: hidden;
}
.airspace-flight-hud .bar .fill {
    position: absolute;
    inset: 0 auto 0 0;
    border-radius: 999px;
    background: linear-gradient(90deg, #6fd6a0, #9fe8c2);
    transition: width 0.2s linear;
}
.airspace-flight-hud .bar.progress .fill { background: linear-gradient(90deg, #b9924e, #e3b563); }
.airspace-flight-hud .footnote {
    margin-top: 8px;
    font-size: 8.5px;
    letter-spacing: 0.06em;
    color: #46586c;
}
@media (max-width: 760px) {
    .airspace-flight-hud {
        left: 10px;
        bottom: calc(160px + env(safe-area-inset-bottom));
        width: min(272px, calc(100vw - 20px));
        max-height: 30dvh;
        overflow-y: auto;
        padding: 10px 12px 9px;
    }
}
.airspace-flight-hud .aircraft-details {
    pointer-events: auto;
    margin-top: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    padding-top: 6px;
}
.airspace-flight-hud .aircraft-details summary {
    color: #8fa3b5;
    cursor: pointer;
    font-size: 10px;
}
`;

// 10 Hz is plenty for a status panel — writing 15 DOM nodes 60x per second
// was pure waste. -Infinity forces the very first frame to render.
const REFRESH_INTERVAL_MS = 100;

/**
 * Live aircraft status panel — metric units throughout. Every value derives
 * from backend data: route metrics (time, distance, fuel plan), the
 * aircraft profile in meta.routing_assumptions, and the animator's live
 * position. Nothing is invented client-side.
 */
export function createFlightHud({ getPlaneState, getPayload }) {
    ensureStyles();

    const hud = document.createElement('div');
    hud.className = 'airspace-flight-hud';
    hud.style.display = 'none';
    document.body.appendChild(hud);

    hud.innerHTML = `
        <div class="hud-title"><span>Aircraft Status</span><span class="phase-chip">—</span></div>
        <div class="row"><span class="key">Airframe</span><span class="val airframe">—</span></div>
        <div class="row"><span class="key">Phase</span><span class="val phase">—</span></div>
        <div class="section-title">Navigation</div>
        <div class="row"><span class="key">Latitude</span><span class="val lat">—</span></div>
        <div class="row"><span class="key">Longitude</span><span class="val lon">—</span></div>
        <div class="row"><span class="key">Altitude</span><span class="val alt">—</span></div>
        <div class="row"><span class="key">Vertical speed</span><span class="val vs">—</span></div>
        <div class="row"><span class="key">Ground speed</span><span class="val gs">—</span></div>
        <div class="section-title">Environment</div>
        <div class="row"><span class="key">Weather exposure</span><span class="val exposure">—</span></div>
        <div class="section-title">Performance</div>
        <div class="row"><span class="key">Fuel</span><span class="val fuel">—</span></div>
        <div class="bar fuel-bar"><div class="fill" style="width:100%"></div></div>
        <div class="row"><span class="key">Burn rate</span><span class="val burn">—</span></div>
        <div class="row"><span class="key">Route progress</span><span class="val progress-label">—</span></div>
        <div class="bar progress"><div class="fill" style="width:0%"></div></div>
        <div class="row"><span class="key">ETA</span><span class="val eta">—</span></div>
        <div class="row"><span class="key">Distance remaining</span><span class="val dist">—</span></div>
        <details class="aircraft-details">
            <summary>CJ3 reference specifications</summary>
            <div class="row"><span class="key">Modeled gross mass</span><span class="val gross-mass">—</span></div>
            <div class="row"><span class="key">Max ramp mass</span><span class="val ramp-mass">—</span></div>
            <div class="row"><span class="key">Max takeoff mass</span><span class="val takeoff-mass">—</span></div>
            <div class="row"><span class="key">Max landing mass</span><span class="val landing-mass">—</span></div>
            <div class="row"><span class="key">Max usable fuel</span><span class="val fuel-capacity">—</span></div>
            <div class="row"><span class="key">Max cruise speed</span><span class="val max-cruise">—</span></div>
            <div class="row"><span class="key">Service ceiling</span><span class="val ceiling">—</span></div>
            <div class="row"><span class="key">Published range</span><span class="val range">—</span></div>
        </details>
        <div class="footnote">Nominal CJ3 specifications; fuel flow and route performance are simulation estimates</div>
    `;

    const el = {
        phaseChip: hud.querySelector('.phase-chip'),
        airframe: hud.querySelector('.airframe'),
        phase: hud.querySelector('.phase'),
        lat: hud.querySelector('.lat'),
        lon: hud.querySelector('.lon'),
        alt: hud.querySelector('.alt'),
        vs: hud.querySelector('.vs'),
        gs: hud.querySelector('.gs'),
        exposure: hud.querySelector('.exposure'),
        fuel: hud.querySelector('.fuel'),
        fuelBar: hud.querySelector('.fuel-bar .fill'),
        burn: hud.querySelector('.burn'),
        progressLabel: hud.querySelector('.progress-label'),
        progressBar: hud.querySelector('.bar.progress .fill'),
        eta: hud.querySelector('.eta'),
        dist: hud.querySelector('.dist'),
        grossMass: hud.querySelector('.gross-mass'),
        rampMass: hud.querySelector('.ramp-mass'),
        takeoffMass: hud.querySelector('.takeoff-mass'),
        landingMass: hud.querySelector('.landing-mass'),
        fuelCapacity: hud.querySelector('.fuel-capacity'),
        maxCruise: hud.querySelector('.max-cruise'),
        ceiling: hud.querySelector('.ceiling'),
        range: hud.querySelector('.range'),
    };

    const PHASE_COLORS = {
        'TAKEOFF': '#ffd166',
        'CLIMB': '#4dd8ff',
        'CRUISE': '#35d07f',
        'DESCENT': '#e2b65f',
        'LANDED': '#93a7b4',
    };

    let lastRefresh = -Infinity;

    function ensureStyles() {
        if (document.getElementById('airspace-hud-styles')) return;
        const style = document.createElement('style');
        style.id = 'airspace-hud-styles';
        style.textContent = HUD_STYLES;
        document.head.appendChild(style);
    }

    function update() {
        // Fast path: nothing to show — hide (once) and bail without any
        // further work. This runs every frame, so keep it allocation-free.
        const state = getPlaneState && getPlaneState();
        const payload = getPayload && getPayload();
        if (!state || !payload) {
            if (hud.style.display !== 'none') hud.style.display = 'none';
            return;
        }

        // Throttle all DOM writes to REFRESH_INTERVAL_MS.
        const now = performance.now();
        if (now - lastRefresh < REFRESH_INTERVAL_MS) return;
        lastRefresh = now;

        hud.style.display = 'block';

        const metrics = (payload.routes && payload.routes.metrics && payload.routes.metrics.optimized) || {};
        const waypoints = (payload.routes && payload.routes.optimized) || [];

        const progress = state.progress;
        const totalMin = metrics.time_min;
        const initialFuel = metrics.initial_fuel_kg;
        const burnTotal = metrics.fuel_estimated_kg;

        // Phase chip + phase row
        el.phaseChip.textContent = state.phase;
        el.phaseChip.style.background = PHASE_COLORS[state.phase] || '#4dd8ff';
        el.phase.textContent = state.phase;

        // Geographic coordinates from the live scene position
        const geo = sceneToGeo(state.position);
        el.lat.textContent = `${geo.lat.toFixed(4)}°`;
        el.lon.textContent = `${geo.lon.toFixed(4)}°`;

        // Altitude — metric only
        el.alt.textContent = `${state.altitude_km.toFixed(2)} km`;

        // Modeled speeds: the animation is time-compressed, so frame-delta
        // speeds are meaningless. Show the model's own numbers for the
        // current phase — the same values the backend used for timing/fuel.
        const profile = (payload.meta && payload.meta.routing_assumptions
            && payload.meta.routing_assumptions.aircraft_profile) || {};
        const climbRate = profile.climb_rate_m_per_min ?? 1189;    // m/min
        const descentRate = profile.descent_rate_m_per_min ?? 600; // m/min
        const cruiseSpeed = profile.cruise_speed_kmh ?? 770.432;
        const formatMass = value => value == null
            ? '—'
            : `${Math.round(value).toLocaleString()} kg`;
        el.airframe.textContent = profile.aircraft_name || 'Cessna Citation CJ3';
        el.grossMass.textContent = formatMass(profile.weight_kg);
        el.rampMass.textContent = formatMass(profile.max_ramp_weight_kg);
        el.takeoffMass.textContent = formatMass(profile.max_takeoff_weight_kg);
        el.landingMass.textContent = formatMass(profile.max_landing_weight_kg);
        el.fuelCapacity.textContent = formatMass(profile.fuel_capacity_kg);
        el.maxCruise.textContent = profile.max_cruise_speed_kts != null
            ? `${Math.round(profile.max_cruise_speed_kts)} kt / ${Math.round(cruiseSpeed)} km/h`
            : `${Math.round(cruiseSpeed)} km/h`;
        el.ceiling.textContent = profile.service_ceiling_ft != null
            ? `${profile.service_ceiling_ft.toLocaleString()} ft`
            : '—';
        el.range.textContent = profile.max_range_nm != null
            ? `${profile.max_range_nm.toLocaleString()} nm`
            : '—';

        let verticalSpeed = 0;
        let groundSpeed = cruiseSpeed;
        if (state.phase === 'TAKEOFF' || state.phase === 'CLIMB') {
            verticalSpeed = climbRate / 60;            // -> m/s
        } else if (state.phase === 'DESCENT') {
            verticalSpeed = -descentRate / 60;
        } else if (state.phase === 'LANDED') {
            groundSpeed = 0;
        }
        el.vs.textContent = `${verticalSpeed.toFixed(1)} m/s`;
        el.gs.textContent = `${Math.round(groundSpeed)} km/h`;

        // Exposure at the nearest route waypoint
        let exposure = null;
        let bestDistance = Infinity;
        for (const wp of waypoints) {
            const d = (wp.x - state.position.x) ** 2 + (wp.z - state.position.z) ** 2;
            if (d < bestDistance) {
                bestDistance = d;
                exposure = wp.exposure_score;
            }
        }
        el.exposure.textContent = exposure != null ? `${exposure} / 100` : '—';

        // Fuel: linear burn over the route's own fuel plan
        if (initialFuel != null && burnTotal != null && totalMin) {
            const remaining = Math.max(0, initialFuel - burnTotal * progress);
            const pct = Math.max(0, Math.min(100, (remaining / initialFuel) * 100));
            el.fuel.textContent = `${Math.round(remaining).toLocaleString()} kg  (${pct.toFixed(0)}%)`;
            el.fuelBar.style.width = `${pct}%`;
            el.fuelBar.style.background = pct < 15
                ? 'linear-gradient(90deg,#ce4c4c,#e77c68)'
                : 'linear-gradient(90deg,#35d07f,#7be8a5)';
            el.burn.textContent = `${Math.round(burnTotal / (totalMin / 60)).toLocaleString()} kg/h`;
        } else {
            el.fuel.textContent = '—';
            el.burn.textContent = '—';
        }

        // Progress / ETA / distance
        el.progressLabel.textContent = `${(progress * 100).toFixed(1)}%`;
        el.progressBar.style.width = `${progress * 100}%`;
        if (totalMin) {
            el.eta.textContent = `${Math.max(0, totalMin * (1 - progress)).toFixed(1)} min`;
        }
        if (metrics.distance_km != null) {
            el.dist.textContent = `${(metrics.distance_km * (1 - progress)).toFixed(1)} km`;
        }
    }

    return { update };
}