import 'package:flutter/material.dart';
import 'package:frontend/utils/overlay_elements/directions.dart';
import 'package:frontend/utils/overlay_elements/plane_info.dart';
import 'package:frontend/utils/overlay_elements/air_title.dart';
import 'package:frontend/utils/overlay_elements/travel_info.dart';
import 'package:frontend/three_view.dart';

class Overlay3js extends StatefulWidget {
  const Overlay3js({super.key});

  @override
  State<Overlay3js> createState() => _Overlay3jsState();
}

class _Overlay3jsState extends State<Overlay3js> {
  bool _isLeftOpen = true;
  bool _isRightOpen = true;

  Map<String, String>? currentFrom;
  Map<String, String>? currentTo;
  List<Map<String, String>>? dynamicPlaneInfo;
  List<Map<String, String>>? dynamicTravelInfo;

  void _handleRouteChanged(Map<String, String>? from, Map<String, String>? to) {
    setState(() {
      currentFrom = from;
      currentTo = to;
    });
    debugPrint('Selected route: ${from?['code']} -> ${to?['code']}');
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        //left pannel
        AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeInOutCubic,
          width: _isLeftOpen ? 290 : 0,
          clipBehavior: Clip.hardEdge,
          decoration: const BoxDecoration(
            color: Color(0xFF14171C),
          ),
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.start,
              children: [
                const AirTitle(),
                const SizedBox(height: 20),
                Directions(
                  onRouteChanged: _handleRouteChanged,
                ),
              ],
            ),
          ),
        ),

        Center(
          child: _buildToggleTab(
            isOpen: _isLeftOpen,
            iconOpen: Icons.chevron_left,
            iconClosed: Icons.chevron_right,
            onTap: () => setState(() => _isLeftOpen = !_isLeftOpen),
          ),
        ),

        const Expanded(
          child: ThreeView(),
        ),
        //left panel
        Center(
          child: _buildToggleTab(
            isOpen: _isRightOpen,
            iconOpen: Icons.chevron_right,
            iconClosed: Icons.chevron_left,
            onTap: () => setState(() => _isRightOpen = !_isRightOpen),
          ),
        ),

        AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeInOutCubic,
          width: _isRightOpen ? 290 : 0,
          clipBehavior: Clip.hardEdge,
          decoration: const BoxDecoration(
            color: Color(0xFF14171C),
          ),
          child: LayoutBuilder(
            builder: (context, constraints) {
              return SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 20),
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    minHeight: constraints.maxHeight - 40,
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      TravelInfo(fields: dynamicTravelInfo),

                      PlaneInfo(fields: dynamicPlaneInfo),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildToggleTab({
    required bool isOpen,
    required IconData iconOpen,
    required IconData iconClosed,
    required VoidCallback onTap,
  }) {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          width: 26,
          height: 64,
          decoration: BoxDecoration(
            color: const Color(0xFF1E222B),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: Colors.white.withValues(alpha: 0.08),
            ),
          ),
          child: Icon(
            isOpen ? iconOpen : iconClosed,
            color: const Color(0xFFFFE306),
            size: 20,
          ),
        ),
      ),
    );
  }
}