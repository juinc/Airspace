import 'package:flutter/material.dart';

import '../models/airspace_models.dart';

/// Baseline vs Optimized comparison. Null-safe: missing values render "—".
class MetricsPanel extends StatelessWidget {
  final RouteMetrics baseline;
  final RouteMetrics optimized;

  const MetricsPanel({
    super.key,
    required this.baseline,
    required this.optimized,
  });

  @override
  Widget build(BuildContext context) {
    final dTime = (optimized.timeMin != null && baseline.timeMin != null)
        ? optimized.timeMin! - baseline.timeMin!
        : null;
    final dFuel =
        (optimized.fuelEstimatedKg != null && baseline.fuelEstimatedKg != null)
            ? optimized.fuelEstimatedKg! - baseline.fuelEstimatedKg!
            : null;
    final dExp = (optimized.avgExposure != null && baseline.avgExposure != null)
        ? optimized.avgExposure! - baseline.avgExposure!
        : null;
    final better = (dTime ?? 0) <= 0 && (dExp ?? 0) <= 0;
    final hasDelta = dTime != null || dFuel != null || dExp != null;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: _glassDecoration(),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _group('BASELINE', baseline, const Color(0xFF5C7086), null),
          const SizedBox(height: 12),
          _group('OPTIMIZED', optimized, const Color(0xFFE3B563), hasDelta
              ? Text(
                  _deltaText(dTime, dFuel, dExp),
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: better
                        ? const Color(0xFF6FD6A0)
                        : const Color(0xFFE2836F),
                  ),
                )
              : null),
        ],
      ),
    );
  }

  Widget _group(String title, RouteMetrics m, Color titleColor, Widget? delta) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(title,
            style: TextStyle(
                fontSize: 9.5,
                fontWeight: FontWeight.w600,
                letterSpacing: 2.4,
                color: titleColor)),
        const SizedBox(height: 5),
        _row('Distance', m.distanceKm == null ? '—' : '${m.distanceKm} km'),
        _row('Time', m.timeMin == null ? '—' : '${m.timeMin} min'),
        _row('Exposure', m.avgExposure == null ? '—' : '${m.avgExposure}'),
        if (delta != null) ...[const SizedBox(height: 4), delta],
      ],
    );
  }

  Widget _row(String key, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 1.5),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(key,
                style:
                    const TextStyle(color: Color(0xFF8FA3B5), fontSize: 11.5)),
            Text(value,
                style: const TextStyle(
                    color: Color(0xFFE9EEF4),
                    fontSize: 12.5,
                    fontWeight: FontWeight.w600)),
          ],
        ),
      );

  String _deltaText(double? dTime, double? dFuel, double? dExp) {
    final parts = <String>[];
    String fmt(double v, String unit, {bool round = false}) =>
        '${v > 0 ? '+' : ''}${round ? v.round().toString() : v.toStringAsFixed(1)} $unit';
    if (dTime != null) parts.add(fmt(dTime, 'min'));
    if (dFuel != null) parts.add(fmt(dFuel, 'kg fuel', round: true));
    if (dExp != null) parts.add(fmt(dExp, 'exp'));
    return 'Δ ${parts.join(' · ')}';
  }
}

BoxDecoration _glassDecoration() => BoxDecoration(
      color: const Color(0xCC0D141E),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: const Color(0x17FFFFFF)),
    );