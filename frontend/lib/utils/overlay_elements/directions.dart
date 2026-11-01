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

  bool _isFromOpen = false;
  bool _isToOpen = false;

  final ScrollController _fromScrollController = ScrollController();
  final ScrollController _toScrollController = ScrollController();

  @override
  void dispose() {
    _fromScrollController.dispose();
    _toScrollController.dispose();
    super.dispose();
  }

  //swap
  void _selectAirport(Map<String, String> airport, bool isFrom) {
    setState(() {
      if (isFrom) {
        if (_selectedTo != null && _selectedTo!['code'] == airport['code']) {
          _selectedTo = _selectedFrom;
        }
        _selectedFrom = airport;
        _isFromOpen = false;
      } else {
        if (_selectedFrom != null && _selectedFrom!['code'] == airport['code']) {
          _selectedFrom = _selectedTo;
        }
        _selectedTo = airport;
        _isToOpen = false;
      }
    });
    widget.onRouteChanged?.call(_selectedFrom, _selectedTo);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1E222B),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.06),
        ),
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
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.5,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          _buildAirportSection(
            label: 'FROM (TAKEOFF)',
            icon: Icons.flight_takeoff,
            airport: _selectedFrom,
            isOpen: _isFromOpen,
            onTap: () {
              setState(() {
                _isFromOpen = !_isFromOpen;
                _isToOpen = false;
              });
            },
          ),
          if (_isFromOpen) ...[
            const SizedBox(height: 6),
            _buildInlineDropdown(
              isFrom: true,
              scrollController: _fromScrollController,
            ),
          ],
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: Divider(
              height: 1,
              thickness: 1,
              color: Colors.white.withValues(alpha: 0.1),
            ),
          ),
          _buildAirportSection(
            label: 'TO (DESTINATION)',
            icon: Icons.flight_land,
            airport: _selectedTo,
            isOpen: _isToOpen,
            onTap: () {
              setState(() {
                _isToOpen = !_isToOpen;
                _isFromOpen = false;
              });
            },
          ),
          if (_isToOpen) ...[
            const SizedBox(height: 6),
            _buildInlineDropdown(
              isFrom: false,
              scrollController: _toScrollController,
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildAirportSection({
    required String label,
    required IconData icon,
    required Map<String, String>? airport,
    required bool isOpen,
    required VoidCallback onTap,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.5),
            fontSize: 10,
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
                color: Colors.white.withValues(alpha: 0.04),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: isOpen
                      ? const Color(0xFFFFE306).withValues(alpha: 0.6)
                      : Colors.white.withValues(alpha: 0.08),
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
                    isOpen ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                    color: Colors.white.withValues(alpha: 0.7),
                    size: 18,
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildInlineDropdown({
    required bool isFrom,
    required ScrollController scrollController,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF14171C),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.1),
        ),
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxHeight: 160),
        child: Scrollbar(
          controller: scrollController,
          thumbVisibility: true,
          child: ListView.separated(
            controller: scrollController,
            shrinkWrap: true,
            padding: const EdgeInsets.symmetric(vertical: 4),
            itemCount: _airports.length,
            separatorBuilder: (_, __) => Divider(
              height: 1,
              color: Colors.white.withValues(alpha: 0.06),
            ),
            itemBuilder: (context, index) {
              final airport = _airports[index];
              final currentTarget = isFrom ? _selectedFrom : _selectedTo;
              final isSelected = currentTarget != null &&
                  currentTarget['code'] == airport['code'];

              return MouseRegion(
                cursor: SystemMouseCursors.click,
                child: ListTile(
                  dense: true,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
                  leading: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: isSelected
                          ? const Color(0xFFFFE306)
                          : Colors.white.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      airport['code']!,
                      style: TextStyle(
                        color: isSelected ? const Color(0xFF14171C) : Colors.white,
                        fontWeight: FontWeight.w800,
                        fontSize: 11,
                      ),
                    ),
                  ),
                  title: Text(
                    airport['city']!,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  subtitle: Text(
                    airport['name'] ?? '',
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.5),
                      fontSize: 10,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                  onTap: () => _selectAirport(airport, isFrom),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}