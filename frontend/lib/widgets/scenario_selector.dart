import 'package:flutter/material.dart';
import 'package:pointer_interceptor/pointer_interceptor.dart';

import '../models/airspace_models.dart';

/// Scenario dropdown — fully native, no HTML in the WebView.
///
/// WHY THIS IS CUSTOM: on Flutter web the 3D scene is an IFrameElement
/// (platform view) that EATS every pointer event over its area — including
/// taps on Flutter widgets drawn on top of it. The stock DropdownButton
/// opens its menu in a plain Overlay route, which the iframe swallows:
/// the button never even opened. This selector renders its menu as an
/// OverlayEntry wrapped in PointerInterceptor (an invisible DOM shield
/// above the iframe), so the button AND the menu are actually clickable.
class ScenarioSelector extends StatefulWidget {
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
  State<ScenarioSelector> createState() => _ScenarioSelectorState();
}

class _ScenarioSelectorState extends State<ScenarioSelector> {
  final LayerLink _link = LayerLink();
  OverlayEntry? _menu;

  void _toggle() => _menu == null ? _open() : _close();

  void _open() {
    final overlay = Overlay.of(context, rootOverlay: true);
    final entry = OverlayEntry(builder: (_) => _buildMenu());
    _menu = entry;
    overlay.insert(entry);
    if (mounted) setState(() {}); // flip the chevron
  }

  void _close() {
    _menu?.remove();
    _menu = null;
    if (mounted) setState(() {});
  }

  void _select(String id) {
    _close();
    if (id != widget.selected) widget.onSelected(id);
  }

  @override
  void dispose() {
    _menu?.remove();
    _menu = null;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selectedTitle = widget.scenarios
        .where((s) => s.id == widget.selected)
        .map((s) => s.title)
        .followedBy([widget.selected])
        .first;

    return CompositedTransformTarget(
      link: _link,
      child: PointerInterceptor(
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: _toggle,
          child: Container(
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
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        selectedTitle,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            color: Color(0xFFE9EEF4), fontSize: 12.5),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Icon(
                      _menu != null ? Icons.expand_less : Icons.expand_more,
                      color: const Color(0xFFE3B563),
                      size: 18,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildMenu() {
    return Stack(
      children: [
        // Fullscreen interceptor barrier: while the menu is open, the
        // iframe cannot eat clicks — any tap outside the menu closes it.
        PointerInterceptor(
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: _close,
            child: const SizedBox.expand(),
          ),
        ),
        CompositedTransformFollower(
          link: _link,
          targetAnchor: Alignment.topRight,
          followerAnchor: Alignment.topRight,
          showWhenUnlinked: false,
          child: PointerInterceptor(
            child: Container(
              width: 264,
              constraints: const BoxConstraints(maxHeight: 330),
              margin: const EdgeInsets.only(top: 6),
              padding: const EdgeInsets.symmetric(vertical: 6),
              decoration: _glassDecoration(),
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: widget.scenarios.length,
                itemBuilder: (context, index) {
                  final scenario = widget.scenarios[index];
                  final isSelected = scenario.id == widget.selected;
                  return GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: () => _select(scenario.id),
                    child: Container(
                      color: isSelected
                          ? const Color(0x26E3B563)
                          : Colors.transparent,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 8),
                      child: Row(
                        children: [
                          SizedBox(
                            width: 18,
                            child: isSelected
                                ? const Icon(Icons.check,
                                    size: 14, color: Color(0xFFE3B563))
                                : null,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              scenario.title,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 12,
                                color: isSelected
                                    ? const Color(0xFFE3B563)
                                    : const Color(0xFFE9EEF4),
                                fontWeight: isSelected
                                    ? FontWeight.w600
                                    : FontWeight.w400,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
        ),
      ],
    );
  }
}

BoxDecoration _glassDecoration() => BoxDecoration(
      color: const Color(0xF00D141E),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: const Color(0x17FFFFFF)),
    );