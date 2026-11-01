import 'dart:convert';

const int airspaceProtocolVersion = 1;
const String airspaceSceneAssetKey =
    'assets/flight-map-3d/dist/build/index.html';

typedef SceneCommandSender = void Function(Map<String, Object?> command);

const Set<String> _sceneEvents = {
  'ready',
  'status',
  'scenarioLoaded',
  'telemetry',
  'coordinateClick',
  'coordinateCleared',
  'error',
};

String? normalizeApiBaseUrl(String value) {
  final uri = Uri.tryParse(value);
  if (uri == null ||
      !uri.hasAuthority ||
      (uri.scheme != 'http' && uri.scheme != 'https') ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      (uri.path.isNotEmpty && uri.path != '/') ||
      uri.hasQuery ||
      uri.hasFragment) {
    return null;
  }
  return '${uri.scheme}://${uri.authority}';
}

/// Parses the v1 envelope used by all native and web scene transports.
Map<String, Object?>? parseSceneEvent(Object? message) {
  Object? decoded = message;
  if (message is String) {
    try {
      decoded = jsonDecode(message);
    } on FormatException {
      return null;
    }
  }
  if (decoded is! Map) return null;

  final event = <String, Object?>{};
  decoded.forEach((key, value) {
    if (key is String) event[key] = value;
  });
  if (event['version'] != airspaceProtocolVersion ||
      event['type'] != 'event' ||
      event['event'] is! String ||
      !_sceneEvents.contains(event['event'])) {
    return null;
  }
  if (event['event'] == 'coordinateClick') {
    const coordinateAliases = {
      'altitudeKm': 'altitude_km',
      'pressureLevel': 'pressure_level',
      'exposureScore': 'exposure_score',
      'fuelRemainingKg': 'fuel_remaining_kg',
    };
    for (final entry in coordinateAliases.entries) {
      if (!event.containsKey(entry.key) && event.containsKey(entry.value)) {
        event[entry.key] = event[entry.value];
      }
    }
  }
  return event;
}

Map<String, Object?> loadScenarioCommand(String scenario) => {
      'version': airspaceProtocolVersion,
      'type': 'command',
      'action': 'loadScenario',
      'scenario': scenario,
    };

Map<String, Object?> setCameraCommand(String preset) => {
      'version': airspaceProtocolVersion,
      'type': 'command',
      'action': 'setCamera',
      'preset': preset,
    };

Map<String, Object?> setApiBaseCommand(String url) => {
      'version': airspaceProtocolVersion,
      'type': 'command',
      'action': 'setApiBase',
      'url': url,
    };

Map<String, Object?> toggleLayerCommand(String layer, bool visible) => {
      'version': airspaceProtocolVersion,
      'type': 'command',
      'action': 'toggleLayer',
      'layer': layer,
      'visible': visible,
    };
