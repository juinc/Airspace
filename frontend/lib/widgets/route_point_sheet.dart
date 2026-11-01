import 'package:flutter/material.dart';
import 'package:pointer_interceptor/pointer_interceptor.dart';

import '../models/airspace_models.dart';

/// Bottom sheet shown when a route point is clicked in the 3D scene.
/// Driven by the `airspace:route-point` bridge payload.
///
/// The root is wrapped in PointerInterceptor: on Flutter web the 3D scene
/// is an IFrameElement that eats every pointer event over its area —
/// without the shield the close button and drag handle are dead.
class RoutePointSheet extends StatelessWidget {
  final RoutePointInfo info;

  const RoutePointSheet({super.key, required this.info});

  static const _routeColors = {
    'baseline': Color(0xFF8FA3B5),
    'previous_optimized': Color(0xFF7A8EA0),
    'optimized': Color(0xFFE3B563),
  };

  static const _phaseColors = {
    'TAKEOFF': Color(0xFFFFD166),
    'CLIMB': Color(0xFF4DD8FF),
    'CRUISE': Color(0xFF35D07F),
    'DESCENT': Color(0xFFE2B65F),
    'LANDED': Color(0xFF93A7B4),
  };

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;
    final maxHeight = MediaQuery.of(context).size.height * 0.72;

    // Pull nullables into locals so Dart can promote them to non-null
    // (field promotion on another object never happens automatically).
    final routeProgress = info.routeProgress;
    final pressureLevel = info.pressureLevel;
    final exposureScore = info.exposureScore;
    final fuelRemainingKg = info.fuelRemainingKg;
    final temperature = info.temperature;
    final windSpeed = info.windSpeed;
    final windDirection = info.windDirection;
    final relativeHumidity = info.relativeHumidity;
    final cloudCover = info.cloudCover;
    final precipitation = info.precipitation;
    final cape = info.cape;

    return PointerInterceptor(
      child: Padding(
        padding: EdgeInsets.only(bottom: bottomInset),
        child: Container(
          constraints: BoxConstraints(maxHeight: maxHeight),
          margin: const EdgeInsets.fromLTRB(10, 0, 10, 10),
          decoration: _glassDecoration(topRadius: 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _buildHeader(context),
              Flexible(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildTitle(),
                      const SizedBox(height: 12),
                      _sectionLabel('POSITION'),
                      _row('Latitude', '${info.lat.toStringAsFixed(5)}°'),
                      _row('Longitude', '${info.lon.toStringAsFixed(5)}°'),
                      _row('Altitude', '${info.altitudeKm.toStringAsFixed(2)} km'),
                      const SizedBox(height: 12),
                      _sectionLabel('ROUTE CONTEXT'),
                      _row(
                        'Route progress',
                        routeProgress == null
                            ? '—'
                            : '${(routeProgress * 100).toStringAsFixed(1)}%',
                      ),
                      _row(
                        'Pressure level',
                        pressureLevel == null ? '—' : '$pressureLevel hPa',
                      ),
                      _row(
                        'Weather exposure',
                        exposureScore == null
                            ? '—'
                            : '${exposureScore.toStringAsFixed(1)} / 100',
                      ),
                      _row('Flight phase', info.phase ?? '—'),
                      _row(
                        'Fuel remaining',
                        fuelRemainingKg == null ? '—' : '$fuelRemainingKg kg',
                      ),
                      const SizedBox(height: 12),
                      _sectionLabel('WEATHER AT NEAREST CELL'),
                      _row(
                        'Temperature',
                        temperature == null
                            ? '—'
                            : '${temperature.toStringAsFixed(1)} °C',
                      ),
                      _row(
                        'Wind',
                        windSpeed == null && windDirection == null
                            ? '—'
                            : [
                                if (windSpeed != null)
                                  '${windSpeed.toStringAsFixed(1)} km/h',
                                if (windDirection != null)
                                  '${windDirection.toStringAsFixed(0)}°',
                              ].join(' · '),
                      ),
                      _row(
                        'Humidity',
                        relativeHumidity == null
                            ? '—'
                            : '${relativeHumidity.toStringAsFixed(0)}%',
                      ),
                      _row(
                        'Cloud cover',
                        cloudCover == null
                            ? '—'
                            : '${cloudCover.toStringAsFixed(0)}%',
                      ),
                      _row(
                        'Precipitation',
                        precipitation == null
                            ? '—'
                            : '${precipitation.toStringAsFixed(1)} mm/h',
                      ),
                      _row(
                        'CAPE',
                        cape == null ? '—' : '${cape.toStringAsFixed(0)} J/kg',
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Weather values come from the nearest grid cell at the '
                        'closest pressure level to the clicked altitude.',
                        style: TextStyle(fontSize: 8.5, color: Color(0xFF46586C)),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // -- Header: drag handle + close button --------------------------------

  Widget _buildHeader(BuildContext context) {
    return Stack(
      alignment: Alignment.center,
      children: [
        Column(
          children: [
            const SizedBox(height: 8),
            Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: const Color(0x33FFFFFF),
                borderRadius: BorderRadius.circular(999),
              ),
            ),
            const SizedBox(height: 8),
          ],
        ),
        Positioned(
          top: 4,
          right: 8,
          child: _CloseButton(onTap: () => Navigator.of(context).maybePop()),
        ),
      ],
    );
  }

  // -- Title: route badge + phase badge -----------------------------------

  Widget _buildTitle() {
    final routeColor = _routeColors[info.route] ?? const Color(0xFF4DD8FF);
    final phaseColor = _phaseColors[info.phase ?? ''] ?? const Color(0xFF4DD8FF);

    return Row(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: routeColor.withValues(alpha: 0.16),
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: routeColor.withValues(alpha: 0.55)),
          ),
          child: Text(
            info.route.toUpperCase(),
            style: TextStyle(
              fontSize: 9.5,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.2,
              color: routeColor,
            ),
          ),
        ),
        const SizedBox(height: 0, width: 8),
        if (info.phase != null)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: phaseColor.withValues(alpha: 0.16),
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: phaseColor.withValues(alpha: 0.55)),
            ),
            child: Text(
              info.phase!,
              style: TextStyle(
                fontSize: 9.5,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.2,
                color: phaseColor,
              ),
            ),
          ),
      ],
    );
  }

  // -- Row helpers ---------------------------------------------------------

  Widget _sectionLabel(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text(
          text,
          style: const TextStyle(
            fontSize: 9,
            fontWeight: FontWeight.w600,
            letterSpacing: 2.4,
            color: Color(0xFF5C7086),
          ),
        ),
      );

  Widget _row(String key, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 1.5),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(key,
                style:
                    const TextStyle(color: Color(0xFF8FA3B5), fontSize: 11.5)),
            Text(
              value,
              style: const TextStyle(
                color: Color(0xFFEEF3F8),
                fontSize: 11.5,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      );
}

class _CloseButton extends StatelessWidget {
  final VoidCallback onTap;

  const _CloseButton({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        width: 30,
        height: 30,
        decoration: BoxDecoration(
          color: const Color(0x14FFFFFF),
          shape: BoxShape.circle,
          border: Border.all(color: const Color(0x2AFFFFFF)),
        ),
        child: const Icon(Icons.close, size: 15, color: Color(0xFF8FA3B5)),
      ),
    );
  }
}

BoxDecoration _glassDecoration({double topRadius = 12}) => BoxDecoration(
      color: const Color(0xF20F1319),
      borderRadius: BorderRadius.only(
        topLeft: Radius.circular(topRadius),
        topRight: Radius.circular(topRadius),
        bottomLeft: Radius.circular(topRadius),
        bottomRight: Radius.circular(topRadius),
      ),
      border: Border.all(color: const Color(0x17FFFFFF)),
    );