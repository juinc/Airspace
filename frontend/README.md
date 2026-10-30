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
