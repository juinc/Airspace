import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_windows/webview_flutter_windows.dart'
    as windows_webview;

import 'airspace_bridge_service.dart';

/// Mobile host: webview_flutter. Events arrive through the
/// 'airspaceChannel' JavaScriptChannel (bridge.js JSON.stringifies into it);
/// commands go through window.airspaceBridge.dispatch(...).
class AirspaceWebviewHost {
  final AirspaceBridgeService bridge;
  WebViewController? _controller;
  windows_webview.WebviewController? _windowsController;
  StreamSubscription<dynamic>? _windowsMessageSubscription;
  Future<void>? _windowsInitialization;
  String? _baseUrl;
  String? _mobileLoadUrl;

  AirspaceWebviewHost(this.bridge);

  Widget buildView(String url) {
    if (Platform.isWindows) {
      _baseUrl = url;
      _windowsInitialization ??= _initializeWindowsWebView(url);
      return FutureBuilder<void>(
        future: _windowsInitialization,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return _PlatformWebViewError(error: snapshot.error.toString());
          }
          final controller = _windowsController;
          if (snapshot.connectionState != ConnectionState.done ||
              controller == null) {
            return const Center(child: CircularProgressIndicator());
          }
          return windows_webview.Webview(controller);
        },
      );
    }

    _baseUrl = url;
    final controller = _controller ??= WebViewController()
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
      );
    if (_mobileLoadUrl != url) {
      _mobileLoadUrl = url;
      unawaited(controller.loadRequest(Uri.parse(url)));
    }

    return WebViewWidget(controller: controller);
  }

  Future<void> _initializeWindowsWebView(String url) async {
    final controller = windows_webview.WebviewController();
    _windowsController = controller;
    _windowsMessageSubscription = controller.webMessage.listen(
      _handleWindowsMessage,
    );
    await controller.initialize();
    await controller.setPopupWindowPolicy(
      windows_webview.WebviewPopupWindowPolicy.deny,
    );
    await controller.loadUrl(url);
  }

  void _handleWindowsMessage(dynamic message) {
    if (message is Map) {
      bridge.handleRawMessage(Map<String, dynamic>.from(message));
    } else if (message is String) {
      try {
        final decoded = jsonDecode(message);
        if (decoded case final Map<String, dynamic> event) {
          bridge.handleRawMessage(event);
        }
      } catch (_) {
        // Ignore messages that do not belong to the Airspace bridge.
      }
    }
  }

  Future<void> dispatch(Map<String, dynamic> command) async {
    if (Platform.isWindows) {
      await _windowsController?.postWebMessage(jsonEncode(command));
      return;
    }
    final controller = _controller;
    if (controller == null) return;
    final encoded = jsonEncode(command);
    await controller.runJavaScript(
      'window.airspaceBridge && window.airspaceBridge.dispatch($encoded);',
    );
  }

  Future<void> reloadWithScenario(String id) async {
    final base = _baseUrl;
    if (base == null) return;
    final uri = Uri.parse(base);
    final query = Map<String, String>.from(uri.queryParameters)
      ..['scenario'] = id;
    if (Platform.isWindows) {
      await _windowsController?.loadUrl(
        uri.replace(queryParameters: query).toString(),
      );
      return;
    }
    final controller = _controller;
    if (controller == null) return;
    await controller.loadRequest(uri.replace(queryParameters: query));
  }

  Future<void> dispose() async {
    await _windowsMessageSubscription?.cancel();
    await _windowsController?.dispose();
  }

  Future<void> loadScenario(String id, {double? routeProgress}) => dispatch({
    'type': 'airspace:loadScenario',
    'scenario': id,
    ...?(routeProgress == null ? null : {'routeProgress': routeProgress}),
  });

  Future<void> setCameraPreset(String preset) =>
      dispatch({'type': 'airspace:setCamera', 'preset': preset});

  Future<void> toggleLayer(String layer, bool visible) => dispatch({
    'type': 'airspace:toggleLayer',
    'layer': layer,
    'visible': visible,
  });

  Future<void> replanWeather() => dispatch({'type': 'airspace:replanWeather'});

  Future<void> clearSelection() =>
      dispatch({'type': 'airspace:clearSelection'});

  Future<void> selectFlight(int index) =>
      dispatch({'type': 'airspace:selectFlight', 'index': index});
}

class _PlatformWebViewError extends StatelessWidget {
  final String error;

  const _PlatformWebViewError({required this.error});

  @override
  Widget build(BuildContext context) => ColoredBox(
    color: const Color(0xFF05080E),
    child: Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
          'Could not start the platform WebView. On Windows, install Edge WebView2. On Linux, install the WebKit GTK runtime libraries.\n\n$error',
          textAlign: TextAlign.center,
          style: const TextStyle(color: Color(0xFF8FA3B5), fontSize: 13),
        ),
      ),
    ),
  );
}
