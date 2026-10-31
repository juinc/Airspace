import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';

class ThreeView extends StatelessWidget {
  const ThreeView({super.key});

  @override
  Widget build(BuildContext context) {
    return HtmlElementView.fromTagName(
      tagName: 'iframe',
      onElementCreated: _configureFrame,
    );
  }

  static void _configureFrame(element) {
    element
      ..setAttribute('src', 'http://localhost:5173')
      ..setAttribute('width', '100%')
      ..setAttribute('height', '100%')
      ..setAttribute(
        'style',
        'border:0;width:100%;height:100%;',
      )
      ..setAttribute('allow', 'fullscreen');
  }
}