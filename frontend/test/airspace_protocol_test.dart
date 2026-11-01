import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/airspace_protocol.dart';

void main() {
  group('v1 scene protocol', () {
    test('normalizes only HTTP(S) backend origins', () {
      expect(
        normalizeApiBaseUrl('http://192.168.1.20:8000/'),
        'http://192.168.1.20:8000',
      );
      expect(
        normalizeApiBaseUrl('https://api.example.test'),
        'https://api.example.test',
      );
      expect(normalizeApiBaseUrl('ftp://host:21'), isNull);
      expect(normalizeApiBaseUrl('http://host:8000/path'), isNull);
      expect(normalizeApiBaseUrl('http://user:pass@host:8000'), isNull);
    });

    test('parses valid object and JSON-string events', () {
      final objectMessage = parseSceneEvent({
        'version': 1,
        'type': 'event',
        'event': 'ready',
        'scenarios': [
          {'id': 'random-storms', 'title': 'Random storms'},
        ],
        'initialScenario': 'random-storms',
      });
      final stringMessage = parseSceneEvent(jsonEncode({
        'version': 1,
        'type': 'event',
        'event': 'status',
        'message': 'Loading',
      }));

      expect(objectMessage?['event'], 'ready');
      expect(stringMessage?['message'], 'Loading');
    });

    test('normalizes known snake-case coordinate fields without overriding v1',
        () {
      final message = parseSceneEvent({
        'version': 1,
        'type': 'event',
        'event': 'coordinateClick',
        'altitude_km': 9.2,
        'pressure_level': 300,
        'exposure_score': 12.5,
        'fuel_remaining_kg': 800,
        'altitudeKm': null,
      });

      expect(message?['altitudeKm'], isNull);
      expect(message?['pressureLevel'], 300);
      expect(message?['exposureScore'], 12.5);
      expect(message?['fuelRemainingKg'], 800);
    });

    test('rejects unknown versions, types, and event names', () {
      expect(
        parseSceneEvent({
          'version': 2,
          'type': 'event',
          'event': 'ready',
        }),
        isNull,
      );
      expect(
        parseSceneEvent({
          'version': 1,
          'type': 'command',
          'event': 'ready',
        }),
        isNull,
      );
      expect(
        parseSceneEvent({
          'version': 1,
          'type': 'event',
          'event': 'unknown',
        }),
        isNull,
      );
    });

    test('builds exact v1 commands', () {
      expect(
        loadScenarioCommand('random-storms'),
        {
          'version': 1,
          'type': 'command',
          'action': 'loadScenario',
          'scenario': 'random-storms',
        },
      );
      expect(
        setCameraCommand('topDown'),
        {
          'version': 1,
          'type': 'command',
          'action': 'setCamera',
          'preset': 'topDown',
        },
      );
      expect(
        setApiBaseCommand('http://192.168.1.20:8000'),
        {
          'version': 1,
          'type': 'command',
          'action': 'setApiBase',
          'url': 'http://192.168.1.20:8000',
        },
      );
      expect(
        toggleLayerCommand('weather', false),
        {
          'version': 1,
          'type': 'command',
          'action': 'toggleLayer',
          'layer': 'weather',
          'visible': false,
        },
      );
    });
  });
}
