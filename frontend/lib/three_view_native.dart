import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';

import 'package:webview_flutter/webview_flutter.dart'
    as mobile;

import 'package:webview_windows/webview_windows.dart'
    as windows;

class ThreeView extends StatefulWidget {
  const ThreeView({super.key});

  @override
  State<ThreeView> createState() => _ThreeViewState();
}

class _ThreeViewState extends State<ThreeView> {
  late final bool isWindows;

  late final windows.WebviewController windowsController;
  mobile.WebViewController? mobileController;

  bool initialized = false;
  String? error;

  @override
  void initState() {
    super.initState();

    isWindows =
        defaultTargetPlatform == TargetPlatform.windows;

    if (isWindows) {
      windowsController = windows.WebviewController();
      initializeWindows();
    } else {
      mobileController = mobile.WebViewController()
        ..setJavaScriptMode(
          mobile.JavaScriptMode.unrestricted,
        )
        ..loadRequest(
          Uri.parse('http://10.0.2.2:5173'),
        );

      initialized = true;
    }
  }

  Future<void> initializeWindows() async {
    try {
      await windowsController.initialize();

      await windowsController.loadUrl(
        'http://localhost:5173',
      );

      if (mounted) {
        setState(() => initialized = true);
      }
    } catch (e) {
      if (mounted) {
        setState(() => error = e.toString());
      }
    }
  }

  @override
  void dispose() {
    if (isWindows) {
      windowsController.dispose();
    }

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (error != null) {
      return Center(child: Text(error!));
    }

    if (!initialized) {
      return const Center(
        child: CircularProgressIndicator(),
      );
    }

    if (isWindows) {
      return windows.Webview(windowsController);
    }

    return mobile.WebViewWidget(
      controller: mobileController!,
    );
  }
}