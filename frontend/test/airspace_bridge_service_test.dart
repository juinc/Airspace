import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/services/airspace_bridge_service.dart';

void main() {
  test('parses scene readiness and scenario metadata', () async {
    final bridge = AirspaceBridgeService();
    final eventFuture = bridge.events.first;

    bridge.handleRawMessage({
      'type': 'airspace:ready',
      'mobile': true,
      'scenarios': [
        {'id': 'storm-wall', 'title': 'Storm wall'},
      ],
    });

    final event = await eventFuture;
    expect(event, isA<AirspaceReady>());
    final ready = event as AirspaceReady;
    expect(ready.mobile, isTrue);
    expect(ready.scenarios, hasLength(1));
    expect(ready.scenarios.single.id, 'storm-wall');
    expect(ready.scenarios.single.title, 'Storm wall');

    bridge.dispose();
  });
}
