import 'package:flutter/material.dart';

class TravelInfo extends StatelessWidget {
  const TravelInfo({super.key, required this.coordinate});

  final Map<String, Object?>? coordinate;

  @override
  Widget build(BuildContext context) {
    final fields = coordinate == null
        ? const <(String, String)>[]
        : _coordinateFields(coordinate!);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1A).withValues(alpha: 0.88),
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.25),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.route, color: Color(0xFFFFE306), size: 18),
              SizedBox(width: 8),
              Text(
                'COORDINATE INSPECTION',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.2,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (coordinate == null)
            Text(
              'Select a route coordinate to inspect it.',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.55),
                fontSize: 12,
              ),
            )
          else if (fields.isEmpty)
            Text(
              'No coordinate details were provided.',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.55),
                fontSize: 12,
              ),
            )
          else
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 220),
              child: SingleChildScrollView(
                child: Column(
                  children: fields
                      .map((field) => _InfoRow(
                            label: field.$1,
                            value: field.$2,
                          ))
                      .toList(),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

List<(String, String)> _coordinateFields(Map<String, Object?> point) {
  const labels = <String, String>{
    'route': 'Route',
    'lat': 'Latitude',
    'lon': 'Longitude',
    'altitudeKm': 'Altitude (km)',
    'pressureLevel': 'Pressure level',
    'exposureScore': 'Exposure score',
    'phase': 'Phase',
    'fuelRemainingKg': 'Fuel remaining (kg)',
  };
  final fields = <(String, String)>[];
  for (final key in labels.keys) {
    final value = point[key];
    if (value == null) continue;
    fields.add((labels[key]!, value.toString()));
  }

  final weather = point['weather'];
  if (weather is Map) {
    for (final entry in weather.entries) {
      if (entry.key is! String || entry.value == null) continue;
      fields.add((
        'Weather · ${entry.key}',
        entry.value.toString(),
      ));
    }
  }
  return fields;
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.6),
                fontSize: 12,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
