import 'package:flutter/material.dart';

import '../models/airspace_models.dart';

/// Bottom sheet shown when the user taps a route in the 3D scene —
/// the native replacement for the old in-WebView inspect panel.
class RoutePointSheet extends StatelessWidget {
  final RoutePointInfo info;

  const RoutePointSheet({super.key, required this.info});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
          16, 16, 16, 16 + MediaQuery.of(context).padding.bottom),
      decoration: const BoxDecoration(
        color: Color(0xFF0C131D),
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 11, vertical: 3),
                decoration: BoxDecoration(
                  color: info.route == 'optimized'
                      ? const Color(0xFFE3B563)
                      : info.route == 'baseline'
                          ? const Color(0xFF5F7F9B)
                          : const Color(0xFF8A97A5),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  info.route.toUpperCase(),
                  style: const TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.4,
                      color: Color(0xFF0A0F16)),
                ),
              ),
              const Spacer(),
              IconButton(
                icon: const Icon(Icons.close,
                    color: Color(0xFF5C7086), size: 18),
                onPressed: () => Navigator.of(context).pop(),
              ),
            ],
          ),
          const SizedBox(height: 10),
          _row('Phase', (info.phase ?? '').toUpperCase()),
          _row('Latitude', '${info.lat.toStringAsFixed(4)}°'),
          _row('Longitude', '${info.lon.toStringAsFixed(4)}°'),
          _row('Altitude', '${info.altitudeKm.toStringAsFixed(2)} km'),
          _row(
              'Progress',
              info.routeProgress == null
                  ? '—'
                  : '${(info.routeProgress! * 100).toStringAsFixed(1)}%'),
          _row('Level',
              info.pressureLevel == null ? '—' : '${info.pressureLevel} hPa'),
          _row('Exposure',
              info.exposureScore == null ? '—' : '${info.exposureScore} / 100'),
          if (info.fuelRemainingKg != null) ...[
            const _SectionTitle('Aircraft'),
            _row('Fuel remaining', '${info.fuelRemainingKg} kg'),
          ],
          const _SectionTitle('Nearest forecast cell'),
          _row('Temperature',
              info.temperature == null ? '—' : '${info.temperature} °C'),
          _row(
              'Wind',
              info.windSpeed == null
                  ? '—'
                  : '${info.windSpeed} km/h${info.windDirection != null ? ' @ ${info.windDirection}°' : ''}'),
          _row('Humidity',
              info.relativeHumidity == null ? '—' : '${info.relativeHumidity} %'),
          _row('Cloud cover',
              info.cloudCover == null ? '—' : '${info.cloudCover} %'),
          _row('Precipitation',
              info.precipitation == null ? '—' : '${info.precipitation} mm'),
          _row('CAPE', info.cape == null ? '—' : '${info.cape} J/kg'),
        ],
      ),
    );
  }

  Widget _row(String key, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 1.5),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(key,
                style: const TextStyle(
                    color: Color(0xFF8FA3B5), fontSize: 12)),
            Text(value,
                style: const TextStyle(
                    color: Color(0xFFEEF3F8),
                    fontSize: 12,
                    fontWeight: FontWeight.w600)),
          ],
        ),
      );
}

class _SectionTitle extends StatelessWidget {
  final String text;
  const _SectionTitle(this.text);

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 10, bottom: 3),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Divider(color: Color(0x14FFFFFF), height: 1),
            const SizedBox(height: 7),
            Text(
              text.toUpperCase(),
              style: const TextStyle(
                  fontSize: 9,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 2.2,
                  color: Color(0xFF5C7086)),
            ),
          ],
        ),
      );
}