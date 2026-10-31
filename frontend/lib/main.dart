/*
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
*/



import 'package:flutter/material.dart';
import 'package:webview_windows/webview_windows.dart';
import 'three_view.dart';
import 'package:frontend/pages/overlay.dart';

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
  final WebviewController _controller = WebviewController();

  bool _isInitialized = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _initializeWebView();
  }

  Future<void> _initializeWebView() async {
    try {
      await _controller.initialize();

      await _controller.loadUrl(
        'http://localhost:5173',
      );

      if (mounted) {
        setState(() {
          _isInitialized = true;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
        });
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          const ThreeView(),
          Overlay_3js(),
        ],
      ),
    );
  }
}
