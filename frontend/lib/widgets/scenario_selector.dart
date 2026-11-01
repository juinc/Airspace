import 'package:flutter/material.dart';

import '../models/airspace_models.dart';

/// Scenario dropdown — fully native, no HTML in the WebView.
class ScenarioSelector extends StatelessWidget {
  final List<ScenarioInfo> scenarios;
  final String selected;
  final ValueChanged<String> onSelected;

  const ScenarioSelector({
    super.key,
    required this.scenarios,
    required this.selected,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: _glassDecoration(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text(
            'WEATHER SCENARIO',
            style: TextStyle(
              fontSize: 9.5,
              fontWeight: FontWeight.w600,
              letterSpacing: 2.4,
              color: Color(0xFF5C7086),
            ),
          ),
          const SizedBox(height: 7),
          DropdownButton<String>(
            value: scenarios.any((s) => s.id == selected) ? selected : null,
            isExpanded: true,
            underline: const SizedBox.shrink(),
            dropdownColor: const Color(0xFF0D141E),
            style: const TextStyle(color: Color(0xFFE9EEF4), fontSize: 12.5),
            icon: const Icon(Icons.expand_more,
                color: Color(0xFFE3B563), size: 18),
            items: scenarios
                .map((s) => DropdownMenuItem(
                      value: s.id,
                      child: Text(s.title, overflow: TextOverflow.ellipsis),
                    ))
                .toList(),
            onChanged: (value) {
              if (value != null) onSelected(value);
            },
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