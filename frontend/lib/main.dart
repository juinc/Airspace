import 'package:flutter/material.dart';
import 'three_view.dart';
import 'package:frontend/utils/overlay_3js.dart';

void main() {
  runApp(const MaterialApp(
    debugShowCheckedModeBanner: false,
    home: ThreeJSView(),
  ));
}

class ThreeJSView extends StatelessWidget {
  const ThreeJSView({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Stack(
        fit: StackFit.expand,
        children: [
          ThreeView(),
          Overlay3js(),
        ],
      ),
    );
  }
}