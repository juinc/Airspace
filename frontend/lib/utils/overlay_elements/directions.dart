import 'package:flutter/material.dart';

class Directions extends StatefulWidget {
  final void Function(Map<String, String>? from, Map<String, String>? to)? onRouteChanged;

  const Directions({super.key, this.onRouteChanged});

  @override
  State<Directions> createState() => _DirectionsState();
}

class _DirectionsState extends State<Directions> {
  static const List<Map<String, String>> _airports = [
    {'code': 'JFK', 'city': 'New York', 'name': 'John F. Kennedy Intl'},
    {'code': 'LHR', 'city': 'London', 'name': 'Heathrow Airport'},
    {'code': 'HND', 'city': 'Tokyo', 'name': 'Haneda Airport'},
    {'code': 'CDG', 'city': 'Paris', 'name': 'Charles de Gaulle'},
    {'code': 'DXB', 'city': 'Dubai', 'name': 'Dubai Intl Airport'},
    {'code': 'FRA', 'city': 'Frankfurt', 'name': 'Frankfurt Airport'},
    {'code': 'SIN', 'city': 'Singapore', 'name': 'Changi Airport'},
    {'code': 'LAX', 'city': 'Los Angeles', 'name': 'Los Angeles Intl'},
    {'code': 'AMS', 'city': 'Amsterdam', 'name': 'Schiphol Airport'},
    {'code': 'SYD', 'city': 'Sydney', 'name': 'Kingsford Smith Airport'},
  ];

  Map<String, String>? _selectedFrom = _airports[0];
  Map<String, String>? _selectedTo = _airports[1];

  void _openAirportPicker({required bool isFrom}) {
    debugPrint('Opening picker for: ${isFrom ? "FROM" : "TO"}');

    showDialog(
      context: context,
      builder: (ctx) {
        return Dialog(
          backgroundColor: const Color(0xFF1A1A1A),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          child: Container(
            width: 360,
            padding: const EdgeInsets.all(18),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      isFrom ? 'SELECT DEPARTURE' : 'SELECT DESTINATION',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 1.5,
                      ),
                    ),
                    IconButton(
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                      icon: const Icon(Icons.close, color: Colors.white70, size: 20),
                      onPressed: () => Navigator.of(ctx).pop(),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 320),
                  child: ListView.separated(
                    shrinkWrap: true,
                    itemCount: _airports.length,
                    separatorBuilder: (_, __) => Divider(
                      height: 1,
                      color: Colors.white.withValues(alpha: 0.08),
                    ),
                    itemBuilder: (context, index) {
                      final airport = _airports[index];
                      final currentTarget = isFrom ? _selectedFrom : _selectedTo;
                      final isSelected = currentTarget != null &&
                          currentTarget['code'] == airport['code'];

                      return ListTile(
                        dense: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        leading: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: isSelected
                                ? const Color(0xFFFFE306)
                                : Colors.white.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            airport['code']!,
                            style: TextStyle(
                              color: isSelected ? const Color(0xFF1A1A1A) : Colors.white,
                              fontWeight: FontWeight.w800,
                              fontSize: 12,
                            ),
                          ),
                        ),
                        title: Text(
                          airport['city']!,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        subtitle: Text(
                          airport['name'] ?? '',
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.6),
                            fontSize: 11,
                          ),
                        ),
                        onTap: () {
                          setState(() {
                            if (isFrom) {
                              _selectedFrom = airport;
                            } else {
                              _selectedTo = airport;
                            }
                          });
                          widget.onRouteChanged?.call(_selectedFrom, _selectedTo);
                          Navigator.of(ctx).pop();
                        },
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Positioned(
      top: 96,
      left: 24,
      child: Material(
        color: Colors.transparent,
        child: Container(
          width: 280,
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
                  Icon(Icons.explore_outlined, color: Color(0xFFFFE306), size: 18),
                  SizedBox(width: 8),
                  Text(
                    'FLIGHT ROUTE',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 2,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),

              _buildAirportSection(
                label: 'FROM (TAKEOFF)',
                icon: Icons.flight_takeoff,
                airport: _selectedFrom,
                onTap: () => _openAirportPicker(isFrom: true),
              ),

              Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Divider(
                  height: 1,
                  thickness: 1,
                  color: Colors.white.withValues(alpha: 0.12),
                ),
              ),

              _buildAirportSection(
                label: 'TO (DESTINATION)',
                icon: Icons.flight_land,
                airport: _selectedTo,
                onTap: () => _openAirportPicker(isFrom: false),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAirportSection({
    required String label,
    required IconData icon,
    required Map<String, String>? airport,
    required VoidCallback onTap,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.5),
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.2,
          ),
        ),
        const SizedBox(height: 6),
        MouseRegion(
          cursor: SystemMouseCursors.click,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onTap,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.05),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: Colors.white.withValues(alpha: 0.1),
                ),
              ),
              child: Row(
                children: [
                  Icon(icon, color: const Color(0xFFFFE306), size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          airport != null
                              ? '${airport['city']} (${airport['code']})'
                              : 'Select Airport',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                        if (airport != null)
                          Text(
                            airport['name'] ?? '',
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.5),
                              fontSize: 10,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                    ],
                  ),
                ),
                Icon(
                  Icons.unfold_more,
                  color: Colors.white.withValues(alpha: 0.5),
                  size: 16,
                ),
              ],
            ),
          ),
        ),
        )
      ],
    );
  }
}