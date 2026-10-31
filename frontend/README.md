# Airspace

The Flutter app displays the Three.js flight scene from a bundled Vite build. Build
the scene before running Flutter so the WebView asset is available:

```sh
cd assets/flight-map-3d
npm install
npm run build
cd ../..
flutter run
```

The Vite build uses relative asset URLs so it can load from Flutter's asset
bundle instead of requiring a development server.

## Synthetic weather scenarios

The Three.js scene loads its weather JSON from the backend. Start the backend
from the repository's `backend` directory:

```sh
python -m uvicorn main:app --reload
```

For the interactive test scene, start Vite in another terminal from
`frontend/assets/flight-map-3d` with `npm run dev`, then open
`http://localhost:5173`.

In the Three.js scenario selector, **A lot more storms** is selected by
default. The other options load reproducible country-wide JSON for random
rain/storm cells or clear airspace. The corresponding backend endpoints are
`GET /test-scenarios/heavy-storms`, `GET /test-scenarios/random-storms`, and
`GET /test-scenarios/clear-airspace`. These fixtures are synthetic and do not
call the live weather API.
