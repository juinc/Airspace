import 'package:flutter/material.dart';
import 'package:frontend/utils/overlay_3js.dart';

void main() {
  runApp(const MaterialApp(
    debugShowCheckedModeBanner: false,
    home: ThreeJSView(),
  ));
}

class ThreeJSView extends StatefulWidget {
  const ThreeJSView({super.key});

  @override
  State<ThreeJSView> createState() => _ThreeJSViewState();
}

class _ThreeJSViewState extends State<ThreeJSView> {
  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF101216),
      body: Overlay3js(),
    );
  }
}