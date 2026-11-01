import 'package:flutter/material.dart';

class TravelInfo extends StatefulWidget {
  final List<Map<String, String>>? fields;

  const TravelInfo({super.key, this.fields});

  @override
  State<TravelInfo> createState() => _TravelInfoState();
}

class _TravelInfoState extends State<TravelInfo> {
  static const List<Map<String, String>> _placeholderFields = [
    {'label': 'Origin', 'value': '—'},
    {'label': 'Destination', 'value': '—'},
    {'label': 'Distance', 'value': '—'},
    {'label': 'ETA', 'value': '—'},
    {'label': 'Duration', 'value': '—'},
    {'label': 'Departure', 'value': '—'},
    {'label': 'Arrival', 'value': '—'},
    {'label': 'Progress', 'value': '—'},
  ];

  late final List<Map<String, String>> _fields;

  @override
  void initState() {
    super.initState();
    _fields = widget.fields ?? _placeholderFields;
  }

  @override
  Widget build(BuildContext context) {
    return Positioned(
      top: 24,
      right: 24,
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
            Row(
              children: [
                const Icon(Icons.route, color: Color(0xFFFFE306), size: 18),
                const SizedBox(width: 8),
                const Text(
                  'TRAVEL INFO',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 2,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            // scrollable, capped
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 260),
              child: SingleChildScrollView(
                child: Column(
                  children: _fields
                      .map((f) => _buildRow(f['label']!, f['value']!))
                      .toList(),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRow(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: Colors.white.withValues(alpha: 0.12),
          ),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.6),
              fontSize: 13,
            ),
          ),
          Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 13,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}