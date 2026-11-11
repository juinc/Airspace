import 'package:flutter/foundation.dart'
    show kIsWeb, defaultTargetPlatform, TargetPlatform;
import 'package:flutter/material.dart';

import 'pages/airspace_page.dart';

/// Scene URL per environment, including the backend API base so the scene
/// works on Android emulators (10.0.2.2 is the host machine's loopback).
String resolveSceneUrl() {
  const scenePort =
      String.fromEnvironment('AIRSPACE_SCENE_PORT', defaultValue: '5173');
  const apiPort =
      String.fromEnvironment('AIRSPACE_API_PORT', defaultValue: '8000');
  const configuredHost = String.fromEnvironment('AIRSPACE_DEV_HOST');

  var host = configuredHost.isNotEmpty ? configuredHost : 'localhost';
  if (configuredHost.isEmpty &&
      !kIsWeb &&
      defaultTargetPlatform == TargetPlatform.android) {
    host = '10.0.2.2';
  }
  return 'http://$host:$scenePort/?api=http://$host:$apiPort';
}

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const AirspaceApp());
}

class AirspaceApp extends StatelessWidget {
  const AirspaceApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Airspace — Executive Flight Intelligence',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF05080E),
      ),
      home: AirspacePage(sceneUrl: resolveSceneUrl()),
    );
  }
}