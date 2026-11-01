import 'dart:convert';
import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import 'airspace_bridge_service.dart';

/// Mobile host: webview_flutter. Events arrive through the
/// 'airspaceChannel' JavaScriptChannel (bridge.js JSON.stringifies into it);
/// commands go through window.airspaceBridge.dispatch(...).
class AirspaceWebviewHost {
  final AirspaceBridgeService bridge;
  WebViewController? _controller;

  AirspaceWebviewHost(this.bridge);

  Widget buildView(String url) {
    // Windows desktop: webview_flutter has no implementation there.
    // Check BEFORE constructing a controller.
    if (Platform.isWindows) {
      return const _UnsupportedPlatform();
    }

    final controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..addJavaScriptChannel(
        'airspaceChannel',
        onMessageReceived: (JavaScriptMessage message) {
          try {
            final decoded = jsonDecode(message.message);
            if (decoded is Map<String, dynamic>) {
              bridge.handleRawMessage(decoded);
            }
          } catch (_) {
            // Not our message — ignore.
          }
        },
      )
      ..loadRequest(Uri.parse(url));
    _controller = controller;

    return WebViewWidget(controller: controller);
  }

  Future<void> dispatch(Map<String, dynamic> command) async {
    final controller = _controller;
    if (controller == null) return;
    final encoded = jsonEncode(command);
    await controller.runJavaScript(
      'window.airspaceBridge && window.airspaceBridge.dispatch($encoded);',
    );
  }

  Future<void> loadScenario(String id, {double? routeProgress}) => dispatch({
        'type': 'airspace:loadScenario',
        'scenario': id,
        if (routeProgress != null) 'routeProgress': routeProgress,
      });

  Future<void> setCameraPreset(String preset) =>
      dispatch({'type': 'airspace:setCamera', 'preset': preset});

  Future<void> toggleLayer(String layer, bool visible) =>
      dispatch({'type': 'airspace:toggleLayer', 'layer': layer, 'visible': visible});

  Future<void> replanWeather() => dispatch({'type': 'airspace:replanWeather'});

  Future<void> clearSelection() => dispatch({'type': 'airspace:clearSelection'});

  Future<void> selectFlight(int index) =>
      dispatch({'type': 'airspace:selectFlight', 'index': index});
}

class _UnsupportedPlatform extends StatelessWidget {
  const _UnsupportedPlatform();

  @override
  Widget build(BuildContext context) => const ColoredBox(
        color: Color(0xFF05080E),
        child: Center(
          child: Text(
            'Windows desktop has no WebView in this build.\n'
            'Run on Chrome (flutter run -d chrome) or an Android device.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Color(0xFF8FA3B5), fontSize: 13),
          ),
        ),
      );
}