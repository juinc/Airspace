import 'package:flutter/material.dart';
import 'package:frontend/pages/main_page.dart';

void main() {
  runApp(const Airspace());
}

class Airspace extends StatelessWidget {
  const Airspace({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Airspace',
      home: const MainPage(),
    );
  }
}