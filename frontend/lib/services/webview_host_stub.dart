import 'package:flutter/widgets.dart';

import 'airspace_bridge_service.dart';

/// Fallback so the analyzer always has a definition. Never used at runtime.
class AirspaceWebviewHost {
  AirspaceWebviewHost(this.bridge);
  final AirspaceBridgeService bridge;
  Widget buildView(String url) =>
      const Center(child: Text('Unsupported platform'));
  Future<void> dispatch(Map<String, dynamic> command) async {}
  Future<void> loadScenario(String id, {double? routeProgress}) async {}
  Future<void> reloadWithScenario(String id) async {}
  Future<void> setCameraPreset(String preset) async {}
  Future<void> toggleLayer(String layer, bool visible) async {}
  Future<void> replanWeather() async {}
  Future<void> clearSelection() async {}
  Future<void> selectFlight(int index) async {}
  Future<void> dispose() async {}
}
