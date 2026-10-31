import 'package:flutter/material.dart';
//import 'package:frontend/utils/overlay_elements/directions.dart';
import 'package:frontend/utils/overlay_elements/plane_info.dart';
import 'package:frontend/utils/overlay_elements/air_title.dart';
import 'package:frontend/utils/overlay_elements/travel_info.dart';
import 'package:frontend/utils/overlay_elements/travel_info.dart';

class Overlay3js extends StatefulWidget {
  const Overlay3js({super.key});

  @override
  State<Overlay3js> createState() => _Overlay3js();
}

class _Overlay3js extends State<Overlay3js> {
  @override
  Widget build(BuildContext context) {
    return SizedBox.expand(
      child: const Stack(
        children: [
          AirTitle(), // top-left
          PlaneInfo(), // bottom-right
          TravelInfo() // top-right
        ],
      ),
    );
  }
}