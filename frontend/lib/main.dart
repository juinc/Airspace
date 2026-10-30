import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:three_js/three_js.dart';

void main() {
  runApp(const Airspace());
}

class Airspace extends StatelessWidget {
  const Airspace({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Demo',
      theme: ThemeData(
        colorScheme: .fromSeed(seedColor: Colors.deepPurple),
      ),
    );
  }
}