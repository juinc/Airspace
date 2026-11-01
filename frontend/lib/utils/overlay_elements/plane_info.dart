import 'package:flutter/material.dart';

class PlaneInfo extends StatelessWidget {
  const PlaneInfo({super.key, this.profile = const {}, required this.telemetry});

  final Map<String, Object?> profile;
  final Map<String, Map<String, Object?>> telemetry;

  @override
  Widget build(BuildContext context) {
    return _InfoCard(
      title: 'FLIGHT TELEMETRY',
      icon: Icons.flight,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _Subheading('AIRCRAFT PROFILE'),
          if (profile.isEmpty)
            const _EmptyMessage('Aircraft profile unavailable.')
          else
            ..._profileFields(profile).map((field) => _InfoRow(
                  label: field.$1,
                  value: field.$2,
                )),
          const SizedBox(height: 10),
          const _Subheading('LIVE FLIGHT STATUS'),
          if (telemetry.isEmpty)
            const _EmptyMessage('Waiting for aircraft telemetry.')
          else
            ...telemetry.entries.map((entry) {
              final fields = _telemetryFields(entry.key, entry.value);
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Column(
                  children: [
                    if (telemetry.length > 1)
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          entry.key,
                          style: const TextStyle(
                            color: Color(0xFFFFE306),
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ...fields.map((field) => _InfoRow(
                          label: field.$1,
                          value: field.$2,
                        )),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }
}

List<(String, String)> _profileFields(Map<String, Object?> profile) {
  const labels = <String, String>{
    'aircraft_name': 'Aircraft',
    'aircraft_variant': 'Variant',
    'cruise_speed_kmh': 'Cruise speed (km/h)',
    'climb_rate_m_per_min': 'Climb rate (m/min)',
    'descent_rate_m_per_min': 'Descent rate (m/min)',
    'fuel_capacity_kg': 'Fuel capacity (kg)',
    'fuel_burn_kg_per_hour': 'Fuel burn (kg/h)',
    'fuel_burn_basis': 'Fuel model',
  };
  final fields = <(String, String)>[];
  for (final entry in profile.entries) {
    if (entry.value == null || entry.value is Map || entry.value is List) {
      continue;
    }
    fields.add((
      labels[entry.key] ?? entry.key.replaceAll('_', ' '),
      _displayValue(entry.value!),
    ));
  }
  return fields;
}

class _Subheading extends StatelessWidget {
  const _Subheading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 5),
        child: Text(
          text,
          style: const TextStyle(
            color: Color(0xFFFFE306),
            fontSize: 10,
            fontWeight: FontWeight.w800,
            letterSpacing: 1.1,
          ),
        ),
      );
}

List<(String, String)> _telemetryFields(
  String flightId,
  Map<String, Object?> data,
) {
  const labels = <String, String>{
    'phase': 'Phase',
    'lat': 'Latitude',
    'lon': 'Longitude',
    'altitudeKm': 'Altitude (km)',
    'groundSpeedKmH': 'Assumed speed (km/h)',
    'verticalSpeedMps': 'Assumed vertical rate (m/s)',
    'progress': 'Progress',
    'exposureScore': 'Exposure score',
    'fuelRemainingKg': 'Estimated fuel remaining (kg)',
    'etaMin': 'ETA (min)',
    'distanceRemainingKm': 'Distance remaining (km)',
  };
  final values = <(String, String)>[('Flight', flightId)];
  for (final entry in data.entries) {
    if (entry.key == 'flightId' ||
        entry.key == 'version' ||
        entry.key == 'type' ||
        entry.key == 'event' ||
        entry.value == null) {
      continue;
    }
    values.add((
      labels[entry.key] ?? entry.key,
      _displayValue(entry.value!),
    ));
  }
  return values;
}

String _displayValue(Object value) {
  if (value is Map || value is List) return value.toString();
  return value.toString();
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({
    required this.title,
    required this.icon,
    required this.child,
  });

  final String title;
  final IconData icon;
  final Widget child;

  @override
  Widget build(BuildContext context) {
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
          Row(
            children: [
              Icon(icon, color: const Color(0xFFFFE306), size: 18),
              const SizedBox(width: 8),
              Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.5,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          child,
        ],
      ),
    );
  }
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

class _EmptyMessage extends StatelessWidget {
  const _EmptyMessage(this.message);

  final String message;

  @override
  Widget build(BuildContext context) => Text(
        message,
        style: TextStyle(
          color: Colors.white.withValues(alpha: 0.55),
          fontSize: 12,
        ),
      );
}
