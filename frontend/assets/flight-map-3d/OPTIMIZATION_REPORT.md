# Airspace 3D Frontend Optimization Report

## Scope

This report covers `frontend/assets/flight-map-3d` only. Backend code was not
changed for this work. Results from Chromium mobile emulation are directional
and are not equivalent to measurements on a physical phone.

## Targets and latest evidence

| Metric | Target | Latest evidence | Status |
|---|---:|---|---|
| Cold load | < 4 s | Earlier emulated runs: 21.0 s baseline and 26.5 s after progressive rendering changes | Not met |
| Scenario switch | < 1 s | Earlier emulated runs: 3.7–6.9 s baseline; one later run: 9.0 s | Not met |
| Mobile frame rate | 60 FPS | Earlier emulated runs: about 7 FPS baseline and 6 FPS later | Not met; device emulation is noisy |
| Initial JavaScript | < 350 KB gzip | Production build: app 25.26 KB + Three.js 147.29 KB = about 172.55 KB gzip; GLTFLoader is lazy-loaded (13.36 KB gzip) | Met for JS chunks |
| GPU memory | < 300 MB | Not measured | Unverified |
| API p95 latency | < 400 ms | Not measured as a p95; one direct local scenario request took 1.15 s | Unverified; sample exceeds target |
| API payload | < 150 KB | One local response was 610,780 bytes uncompressed; prior local gzip estimates were 17–48 KB, but wire compression was not verified | Unverified |
| Draw calls | < 50 | Earlier emulated runs measured 64, then 57 | Not met |

The current benchmark was attempted against the local dev server, but a
scenario-switch request was aborted before a complete run could be collected.
Do not treat that attempt as a successful benchmark or as a new performance
measurement.

## Changes present in the frontend

- Mobile terrain and aircraft variants reduce the asset sizes from about
  28.57 MB to 3.38 MB for terrain, and from about 1.78 MB to 211 KB for the
  aircraft. The terrain variant contains about 166k vertices.
- Three.js is split from the application bundle, and `GLTFLoader` is imported
  lazily.
- Mobile rendering caps pixel ratio and disables antialiasing; shadows and
  post-processing are disabled.
- Weather rendering is deferred until the initial route is visible, and the
  rendered weather-cell count is capped.
- Scenario changes now abort a superseded frontend request. This prevents
  stale requests from competing with the selected scenario and avoids logging
  cancellation of an outdated request as an active scenario failure.
- A repeatable Playwright benchmark is available with `npm run benchmark`.

The production build still reports a >500 KB minified Three.js chunk before
gzip. The compressed initial-JavaScript target is met, but splitting or
reducing the uncompressed vendor chunk remains a possible improvement.

## Remaining work

The cold-load, scenario-switch, frame-rate, and draw-call targets remain unmet
or unverified. Run the benchmark against a stable local backend and production
preview, then profile on a representative physical mobile device before
claiming these targets. API latency and compression require backend-side
measurement and are outside this frontend-only scope.
