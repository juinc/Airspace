import 'package:flutter/material.dart';

import '../models/airspace_models.dart';

/// Pressure layer legend — colors arrive from the scene so they always
/// match the rendered altitude outlines exactly.
///
/// The panel carries its own fixed width so it is safe inside any parent
/// (Row, Stack/Positioned, overlay) — a scrollable viewport requires a
/// bounded cross-axis, and an unconstrained parent previously crashed the
/// layout with "Viewport has unbounded width" on web.
class PressureLegend extends StatelessWidget {
  final List<PressureLevelInfo> levels;

  static const double _panelWidth = 210.0;

  const PressureLegend({super.key, required this.levels});

  @override
  Widget build(BuildContext context) {
    if (levels.isEmpty) return const SizedBox.shrink();
    return Container(
      width: _panelWidth,
      constraints: const BoxConstraints(maxHeight: 180),
      padding: const EdgeInsets.all(12),
      decoration: _glassDecoration(),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'PRESSURE LAYERS',
            style: TextStyle(
                fontSize: 9.5,
                fontWeight: FontWeight.w600,
                letterSpacing: 2.4,
                color: Color(0xFF5C7086)),
          ),
          const SizedBox(height: 8),
          // Few levels (4 pressure levels) — a scrollable viewport is
          // unnecessary overhead and was the crash source. Plain children
          // keep the Column naturally sized under the 180 px cap.
          for (final level in levels)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                children: [
                  Container(
                    width: 9,
                    height: 9,
                    decoration: BoxDecoration(
                      color: Color(level.colorValue),
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                            color: Color(level.colorValue),
                            blurRadius: 6,
                            spreadRadius: 0),
                      ],
                    ),
                  ),
                  const SizedBox(width: 9),
                  Expanded(
                    child: Text('${level.pressure} hPa',
                        style: const TextStyle(
                            color: Color(0xFFE9EEF4), fontSize: 11.5)),
                  ),
                  Text('${level.altitudeKm.toStringAsFixed(1)} km',
                      style: const TextStyle(
                          color: Color(0xFF8FA3B5), fontSize: 11.5)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

BoxDecoration _glassDecoration() => BoxDecoration(
      color: const Color(0xCC0D141E),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: const Color(0x17FFFFFF)),
    );