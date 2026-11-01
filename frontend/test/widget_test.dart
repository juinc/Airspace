import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/utils/overlay_elements/plane_info.dart';
import 'package:frontend/utils/overlay_elements/travel_info.dart';

void main() {
  testWidgets('route and flight panels render only supplied scene values',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 262,
            height: 700,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                TravelInfo(
                  coordinate: {
                    'route': 'optimized',
                    'lat': 46.2,
                    'lon': 24.0,
                    'altitudeKm': 9.2,
                    'pressureLevel': 300,
                    'exposureScore': null,
                    'weather': {'temperature': 4.1},
                  },
                ),
                PlaneInfo(
                  telemetry: {
                    'flight-1': {
                      'flightId': 'flight-1',
                      'phase': 'cruise',
                      'altitudeKm': 9.2,
                      'groundSpeedKmH': 780,
                      'fuelRemainingKg': null,
                    },
                  },
                ),
              ],
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.text('COORDINATE INSPECTION'), findsOneWidget);
    expect(find.text('Latitude'), findsOneWidget);
    expect(find.text('46.2'), findsOneWidget);
    expect(find.text('Weather · temperature'), findsOneWidget);
    expect(find.text('FLIGHT TELEMETRY'), findsOneWidget);
    expect(find.text('cruise'), findsOneWidget);
    expect(find.text('780'), findsOneWidget);
    expect(find.text('Aircraft'), findsNothing);
    expect(find.text('—'), findsNothing);
  });
}
