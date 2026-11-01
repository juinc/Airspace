import 'package:flutter/material.dart';

import '../models/airspace_models.dart';

/// Live aircraft status — driven by 10 Hz `airspace:flight-state`.
/// All math is done in the WebView (single source of truth); this widget
/// only formats. Null values render "—".
///
/// In multi-flight scenarios, a chip row lets the user pick which aircraft
/// feeds the HUD; clicking a plane in the 3D scene does the same.
class AircraftStatusCard extends StatelessWidget {
  final FlightState state;
  final AircraftProfileInfo aircraft;
  final int flightCount;
  final List<FlightInfo> flights;
  final int selectedIndex;
  final ValueChanged<int>? onSelectFlight;

  const AircraftStatusCard({
    super.key,
    required this.state,
    required this.aircraft,
    this.flightCount = 1,
    this.flights = const [],
    this.selectedIndex = 0,
    this.onSelectFlight,
  });

  static const _phaseColors = {
    'TAKEOFF': Color(0xFFFFD166),
    'CLIMB': Color(0xFF4DD8FF),
    'CRUISE': Color(0xFF35D07F),
    'DESCENT': Color(0xFFE2B65F),
    'LANDED': Color(0xFF93A7B4),
  };

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 272,
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 10),
      decoration: _glassDecoration(),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'AIRCRAFT STATUS',
                style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 2.4,
                    color: Color(0xFF5C7086)),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                decoration: BoxDecoration(
                  color: _phaseColors[state.phase] ?? const Color(0xFF4DD8FF),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  state.phase,
                  style: const TextStyle(
                      fontSize: 9.5,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1,
                      color: Color(0xFF0A0F16)),
                ),
              ),
            ],
          ),
          if (flightCount > 1) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              runSpacing: 4,
              children: [
                for (int i = 0; i < flightCount; i++) _flightChip(i),
              ],
            ),
          ],
          const SizedBox(height: 8),
          _row('Airframe', aircraft.name ?? 'Cessna Citation CJ3'),
          _row('Latitude', '${state.lat.toStringAsFixed(4)}°'),
          _row('Longitude', '${state.lon.toStringAsFixed(4)}°'),
          _row('Altitude', '${state.altitudeKm.toStringAsFixed(2)} km'),
          _row('Vertical speed',
              '${state.verticalSpeedMS.toStringAsFixed(1)} m/s'),
          _row('Ground speed', '${state.groundSpeedKmh.round()} km/h'),
          _row('Weather exposure',
              state.exposureScore == null ? '—' : '${state.exposureScore} / 100'),
          const _Divider(),
          _row('Fuel', state.fuelRemainingKg == null
              ? '—'
              : '${state.fuelRemainingKg} kg (${state.fuelPercent ?? 0}%)'),
          _fuelBar(state.fuelPercent ?? 100),
          _row('Burn rate',
              state.burnRateKgPerH == null ? '—' : '${state.burnRateKgPerH} kg/h'),
          _row('Route progress', '${(state.progress * 100).toStringAsFixed(1)}%'),
          _progressBar(state.progress),
          _row('ETA', state.etaMin == null ? '—' : '${state.etaMin} min'),
          _row('Distance remaining',
              state.distanceRemainingKm == null ? '—' : '${state.distanceRemainingKm} km'),
          const SizedBox(height: 6),
          const Text(
            'Nominal CJ3 specs; fuel flow and route performance are simulation estimates',
            style: TextStyle(fontSize: 8.5, color: Color(0xFF46586C)),
          ),
        ],
      ),
    );
  }

  Widget _flightChip(int index) {
    final selected = index == selectedIndex;
    final label = (index < flights.length && flights[index].id.isNotEmpty)
        ? flights[index].id
        : 'F${index + 1}';
    return GestureDetector(
      onTap: () => onSelectFlight?.call(index),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: selected ? const Color(0xFFE3B563) : const Color(0x14FFFFFF),
          borderRadius: BorderRadius.circular(999),
          border: Border.all(
              color: selected
                  ? const Color(0xFFE3B563)
                  : const Color(0x2AFFFFFF)),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 9.5,
            fontWeight: FontWeight.w700,
            letterSpacing: 1,
            color: selected ? const Color(0xFF0A0F16) : const Color(0xFF8FA3B5),
          ),
        ),
      ),
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
                    color: Color(0xFFEEF3F8),
                    fontSize: 11.5,
                    fontWeight: FontWeight.w600)),
          ],
        ),
      );

  Widget _fuelBar(int percent) {
    final low = percent < 15;
    return _bar(
      percent.toDouble(),
      low
          ? const LinearGradient(
              colors: [Color(0xFFCE4C4C), Color(0xFFE77C68)])
          : const LinearGradient(
              colors: [Color(0xFF35D07F), Color(0xFF7BE8A5)]),
    );
  }

  Widget _progressBar(double progress) => _bar(
        progress * 100,
        const LinearGradient(colors: [Color(0xFFB9924E), Color(0xFFE3B563)]),
      );

  Widget _bar(double percent, Gradient gradient) => Container(
        height: 5,
        margin: const EdgeInsets.symmetric(vertical: 4),
        decoration: BoxDecoration(
          color: const Color(0x12FFFFFF),
          borderRadius: BorderRadius.circular(999),
        ),
        clipBehavior: Clip.antiAlias,
        alignment: Alignment.centerLeft,
        child: FractionallySizedBox(
          widthFactor: (percent / 100).clamp(0.0, 1.0),
          child: Container(decoration: BoxDecoration(gradient: gradient)),
        ),
      );
}

class _Divider extends StatelessWidget {
  const _Divider();

  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.symmetric(vertical: 6),
        child: Divider(color: Color(0x14FFFFFF), height: 1),
      );
}

BoxDecoration _glassDecoration() => BoxDecoration(
      color: const Color(0xE00F1319),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: const Color(0x17FFFFFF)),
    );