const LABELS = {
    aircraft_name: 'Aircraft',
    aircraft_variant: 'Variant',
    cruise_speed_kmh: 'Cruise speed (km/h)',
    climb_rate_m_per_min: 'Climb rate (m/min)',
    descent_rate_m_per_min: 'Descent rate (m/min)',
    fuel_capacity_kg: 'Fuel capacity (kg)',
    fuel_burn_kg_per_hour: 'Fuel burn (kg/h)',
    distance_km: 'Distance (km)',
    time_min: 'Flight time (min)',
    fuel_estimated_kg: 'Estimated fuel (kg)',
    fuel_remaining_kg: 'Fuel remaining (kg)',
    avg_exposure: 'Average exposure',
    max_exposure: 'Maximum exposure',
    origin: 'Origin',
    destination: 'Destination',
    phase: 'Phase',
    altitudeKm: 'Altitude (km)',
    groundSpeedKmH: 'Ground speed (km/h)',
    verticalSpeedMps: 'Vertical speed (m/s)',
    etaMin: 'ETA (min)',
    distanceRemainingKm: 'Distance remaining (km)',
    fuelRemainingKg: 'Fuel remaining (kg)',
    exposureScore: 'Exposure score',
    lat: 'Latitude',
    lon: 'Longitude',
};

const LAYERS = ['weather', 'routes', 'airports', 'altitude'];

export function mountStandaloneUi({ scenarios, initialScenario, sendCommand }) {
    const root = document.createElement('section');
    root.className = 'airspace-ui';
    root.innerHTML = `
      <header class="airspace-toolbar">
        <strong>✈ AIRSPACE</strong>
        <span class="airspace-status" aria-live="polite">Loading scene…</span>
        <select aria-label="Weather scenario"></select>
        <button data-camera="overview">Overview</button>
        <button data-camera="topDown">Top down</button>
        <button class="airspace-reload" aria-label="Reload scenario">↻</button>
      </header>
      <nav class="airspace-layers" aria-label="Scene layers"></nav>
      <div class="airspace-details" aria-label="Flight information">
        <article class="airspace-card"><h2>FLIGHT STATUS</h2><p>Waiting for scenario data.</p></article>
        <article class="airspace-card"><h2>AIRCRAFT & ROUTES</h2><p>Aircraft profile and route metrics will appear here.</p></article>
        <article class="airspace-card"><h2>LIVE FLIGHTS</h2><p>Waiting for aircraft telemetry.</p></article>
        <article class="airspace-card"><h2>COORDINATE INSPECTION</h2><p>Select a route coordinate to inspect it.</p></article>
      </div>`;

    const style = document.createElement('style');
    style.textContent = `
      .airspace-ui{position:absolute;inset:0;z-index:5;color:#f4f6fa;font:13px/1.4 system-ui,sans-serif;pointer-events:none}
      .airspace-toolbar,.airspace-layers,.airspace-card{background:rgba(17,21,29,.92);border:1px solid rgba(255,255,255,.11);box-shadow:0 8px 24px #0005;backdrop-filter:blur(10px)}
      .airspace-toolbar{pointer-events:auto;position:absolute;top:max(12px,env(safe-area-inset-top));left:12px;right:12px;min-height:48px;padding:8px 10px;border-radius:12px;display:flex;align-items:center;gap:8px}
      .airspace-toolbar strong{white-space:nowrap;color:#ffe306;letter-spacing:1px}.airspace-status{flex:1;min-width:50px;color:#b5bdca;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .airspace-toolbar select,.airspace-toolbar button,.airspace-layers button{color:#eef1f6;background:#252b36;border:1px solid #ffffff20;border-radius:7px;padding:7px 9px;font:inherit}
      .airspace-toolbar select{max-width:min(240px,32vw)}.airspace-toolbar button,.airspace-layers button{cursor:pointer}.airspace-toolbar button:hover,.airspace-layers button:hover{border-color:#ffe306}
      .airspace-layers{pointer-events:auto;position:absolute;top:72px;left:12px;padding:6px;border-radius:9px;display:flex;gap:5px}.airspace-layers button[aria-pressed="true"]{color:#ffe306}
      .airspace-details{pointer-events:auto;position:absolute;left:12px;right:12px;bottom:max(12px,env(safe-area-inset-bottom));display:flex;gap:9px;overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x mandatory;padding:2px 2px 8px;scrollbar-color:#697384 #171b23}
      .airspace-card{flex:0 0 min(310px,84vw);max-height:min(34vh,260px);overflow:auto;border-radius:12px;padding:12px;scroll-snap-align:start}
      .airspace-card h2{font-size:11px;letter-spacing:1.2px;margin:0 0 8px;color:#ffe306}.airspace-card p{color:#aeb7c4;margin:4px 0}
      .airspace-row{display:flex;justify-content:space-between;gap:12px;padding:4px 0;border-bottom:1px solid #ffffff0d}.airspace-row span:first-child{color:#aeb7c4}.airspace-row span:last-child{text-align:right;overflow-wrap:anywhere}
      @media(max-width:650px){.airspace-toolbar{flex-wrap:wrap}.airspace-status{order:3;flex-basis:100%}.airspace-layers{top:106px;max-width:calc(100% - 24px);overflow:auto}.airspace-details{left:8px;right:8px}.airspace-card{max-height:30vh}}
      @media(max-height:600px){.airspace-card{max-height:38vh}.airspace-layers{top:68px}}
    `;
    document.head.append(style);
    document.getElementById('app')?.append(root);

    const status = root.querySelector('.airspace-status');
    const selector = root.querySelector('select');
    for (const scenario of scenarios) {
        const option = document.createElement('option');
        option.value = scenario.id;
        option.textContent = scenario.title;
        selector.append(option);
    }
    selector.value = initialScenario;
    const layerState = Object.fromEntries(LAYERS.map(layer => [layer, true]));
    const layerBar = root.querySelector('.airspace-layers');
    for (const layer of LAYERS) {
        const button = document.createElement('button');
        button.textContent = layer[0].toUpperCase() + layer.slice(1);
        button.setAttribute('aria-pressed', 'true');
        button.addEventListener('click', () => {
            layerState[layer] = !layerState[layer];
            button.setAttribute('aria-pressed', String(layerState[layer]));
            sendCommand({ action: 'toggleLayer', layer, visible: layerState[layer] });
        });
        layerBar.append(button);
    }
    selector.addEventListener('change', () => sendCommand({ action: 'loadScenario', scenario: selector.value }));
    root.querySelector('.airspace-reload').addEventListener('click', () => sendCommand({ action: 'loadScenario', scenario: selector.value }));
    root.querySelectorAll('[data-camera]').forEach(button => button.addEventListener('click', () => {
        sendCommand({ action: 'setCamera', preset: button.dataset.camera });
    }));

    const cards = [...root.querySelectorAll('.airspace-card')];
    const onEvent = ({ detail }) => {
        if (!detail || detail.type !== 'event') return;
        if (detail.event === 'ready') {
            status.textContent = 'Scene ready';
        } else if (detail.event === 'status' || detail.event === 'error') {
            status.textContent = detail.message || 'Scene error';
        } else if (detail.event === 'scenarioLoaded') {
            selector.value = detail.scenario || selector.value;
            status.textContent = `Loaded ${selector.selectedOptions[0]?.textContent || selector.value}`;
            renderCard(cards[0], 'FLIGHT STATUS', {
                Scenario: detail.meta?.title || detail.scenario,
                'Weather events': detail.eventCount,
                'Flights': (detail.flights || []).map(flight => `${flight.id} (${flight.origin || '?'} → ${flight.destination || '?'})`).join(', '),
                Source: detail.meta?.source,
                'Trajectory status': detail.meta?.trajectoryStatus,
            });
            const profile = detail.meta?.aircraftProfile || {};
            const routeData = {};
            cards[2].dataset.telemetry = '{}';
            for (const flight of detail.flights || []) {
                routeData[flight.id] = { origin: flight.origin, destination: flight.destination, ...(flight.metrics || {}) };
            }
            renderCard(cards[1], 'AIRCRAFT & ROUTES', { 'Aircraft profile': profile, Flights: routeData });
            renderCard(cards[2], 'LIVE FLIGHTS', {}, 'Waiting for aircraft telemetry…');
            renderCard(cards[3], 'COORDINATE INSPECTION', {}, 'Select a route coordinate to inspect it.');
        } else if (detail.event === 'telemetry') {
            const key = `telemetry:${detail.flightId || 'Flight'}`;
            const telemetry = JSON.parse(cards[2].dataset.telemetry || '{}');
            telemetry[key] = detail;
            cards[2].dataset.telemetry = JSON.stringify(telemetry);
            renderCard(cards[2], 'LIVE FLIGHTS', telemetry);
        } else if (detail.event === 'coordinateClick') {
            renderCard(cards[3], 'COORDINATE INSPECTION', detail);
        } else if (detail.event === 'coordinateCleared') {
            renderCard(cards[3], 'COORDINATE INSPECTION', {}, 'Select a route coordinate to inspect it.');
        }
    };
    window.addEventListener('airspace:bridge', onEvent);
    return () => {
        window.removeEventListener('airspace:bridge', onEvent);
        root.remove();
        style.remove();
    };
}

function renderCard(card, title, values, emptyMessage = 'No flight details reported.') {
    card.replaceChildren();
    const heading = document.createElement('h2');
    heading.textContent = title;
    card.append(heading);
    const rows = [];
    flatten(values, '', rows);
    if (!rows.length) {
        const empty = document.createElement('p');
        empty.textContent = emptyMessage;
        card.append(empty);
        return;
    }
    for (const [label, value] of rows) {
        const row = document.createElement('div');
        row.className = 'airspace-row';
        const name = document.createElement('span');
        name.textContent = LABELS[label] || label.replaceAll('_', ' ');
        const text = document.createElement('span');
        text.textContent = value;
        row.append(name, text);
        card.append(row);
    }
}

function flatten(value, prefix, rows) {
    if (value == null || value === '') return;
    if (typeof value === 'object') {
        for (const [key, nested] of Object.entries(value)) {
            if (['version', 'type', 'event'].includes(key)) continue;
            flatten(nested, prefix ? `${prefix} · ${key}` : key, rows);
        }
        return;
    }
    const formatted = typeof value === 'number' ? Number(value.toFixed(2)).toString() : String(value);
    rows.push([prefix || 'Value', formatted]);
}
