# Flutter ↔ Three.js bridge protocol (v1)

Flutter and the scene use JSON messages with `version: 1`. Flutter does not
recompute coordinates, weather, exposure, or route metrics; it displays the
values sent by the scene.

## Flutter → scene commands

```json
{"version":1,"type":"command","action":"loadScenario","scenario":"<id>"}
{"version":1,"type":"command","action":"setCamera","preset":"overview"}
{"version":1,"type":"command","action":"setCamera","preset":"topDown"}
{"version":1,"type":"command","action":"toggleLayer","layer":"weather","visible":true}
{"version":1,"type":"command","action":"setApiBase","url":"http://host:8000"}
```

`toggleLayer.layer` is one of `weather`, `routes`, `airports`, or `altitude`.
Flutter sends the desired visibility, not a toggle-only signal. The UI starts
with all four controls selected and synchronizes them after scenario data is
loaded. Scenario IDs are taken only from `ready.scenarios`; the list from the
scene is authoritative and Flutter does not maintain a separate scenario
allowlist. Flutter requests `ready.initialScenario` after receiving `ready`;
embedded scenes otherwise wait for an explicit `loadScenario` command.

## Scene → Flutter events

Every event uses `{ "version": 1, "type": "event", "event": ... }`.

- `ready`: `scenarios: [{id,title}]`, `initialScenario`
- `status`: `message`, optional `scenario`
- `scenarioLoaded`: `scenario`, `meta`, `metrics`, `flights`,
  `pressureLevels`, `eventCount`
- `telemetry`: `flightId`, `phase`, `lat`, `lon`, `altitudeKm`,
  `groundSpeedKmH`, `verticalSpeedMps`, `progress`, `exposureScore`,
  `fuelRemainingKg`, `etaMin`, `distanceRemainingKm`
- `coordinateClick`: `route`, `lat`, `lon`, `altitudeKm`, `pressureLevel`,
  `exposureScore`, `phase`, `fuelRemainingKg`, `weather`
- `coordinateCleared`
- `error`: `message`, optional `scenario`

The current scenario IDs are provided by the scene at runtime. They include
`random-storms`, `heavy-storms`, `clear-airspace`, `layered-random`, and the
other scenario IDs registered by the scene. The Flutter selector does not
assume a fixed list.

`scenarioLoaded.pressureLevels` may contain `{pressure, altitudeKm}` objects.
Per-flight metrics are read from `flights[].metrics`; top-level `metrics` is
used as the fallback for the first flight. The UI renders supplied metric
values and does not infer aircraft profile fields. Null values are omitted.
Telemetry speed and vertical-rate values are model assumptions from the
backend aircraft profile, not live aircraft measurements; unavailable values
are sent as `null`.

## Platform transport

- Android/iOS: Flutter registers the `AirspaceBridge` JavaScript channel.
  Scene events are JSON strings posted with
  `AirspaceBridge.postMessage(JSON.stringify(event))`. Flutter commands call
  `window.AirspaceThree.receiveMessage(command)` in the WebView.
- Windows: the scene posts JSON strings with
  `window.chrome.webview.postMessage(JSON.stringify(event))`; Flutter consumes
  `webview_windows.WebviewController.webMessage`. Flutter commands call
  `window.AirspaceThree.receiveMessage(command)` in the WebView.
- Flutter web: the scene posts events to `window.parent` with
  `window.parent.postMessage(event, '*')`; Flutter filters messages to its
  scene iframe. Commands are posted to that iframe's `contentWindow`.

Flutter queues commands until it receives `ready`. It sends the selected API
base after readiness and offers a reload action for the currently selected
scenario after changing the host. Native WebViews invoke the scene's
`window.AirspaceThree.receiveMessage(command)` entry point; Flutter web uses
the parent-window message listener.

The route inspector's current event contains the coordinate payload; Flutter
prefers the v1 camelCase fields and recognizes the existing snake_case
altitude/pressure/exposure/fuel aliases only when the corresponding v1 field
is absent.

## Backend address and packaged scene

The Flutter app loads the packaged Vite output at
`assets/flight-map-3d/dist/build/index.html`; it no longer assumes a Vite dev
server at `localhost:5173`. Run `npm run build` in `frontend/assets/flight-map-3d`
before building/running Flutter. Mobile platforms use Flutter's asset-backed
WebView loader, Windows serves those bundled assets from an app-local loopback
server, and Flutter web loads the packaged asset into its iframe.

The backend base URL is editable in the Flutter controls and can be set at
build time with `--dart-define=AIRSPACE_API_BASE=http://host:8000`. The scene's
Android-emulator default is `http://10.0.2.2:8000`; Flutter does not assume
that address because it cannot distinguish an emulator from a physical
Android phone. On a physical device, enter the development computer's
reachable LAN address (for example `http://192.168.1.20:8000`). The backend
must listen on a network-reachable interface and the host firewall must allow
the connection (for local development, start Uvicorn with `--host 0.0.0.0`).
HTTP is enabled for this local development workflow on Android. On iOS, use a
reachable HTTPS endpoint unless the app's App Transport Security policy is
explicitly configured for the chosen development host.

The status, scenario metrics, coordinate inspection, and flight telemetry
panels update only from v1 scene events. No telemetry values or aircraft
attributes are synthesized by Flutter.
