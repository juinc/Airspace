import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart' as mobile;
import 'package:webview_windows/webview_windows.dart' as windows;

import 'airspace_protocol.dart';

class ThreeView extends StatefulWidget {
  const ThreeView({
    super.key,
    required this.onSceneEvent,
    required this.onCommandSenderReady,
    this.backendBaseUrl,
  });

  final ValueChanged<Map<String, Object?>> onSceneEvent;
  final ValueChanged<SceneCommandSender> onCommandSenderReady;
  final String? backendBaseUrl;

  @override
  State<ThreeView> createState() => _ThreeViewState();
}

class _ThreeViewState extends State<ThreeView> {
  late final bool _isWindows =
      defaultTargetPlatform == TargetPlatform.windows;
  windows.WebviewController? _windowsController;
  mobile.WebViewController? _mobileController;
  StreamSubscription<dynamic>? _windowsMessageSubscription;
  HttpServer? _assetServer;
  final List<Map<String, Object?>> _pendingCommands = [];
  Future<void> _commandQueue = Future<void>.value();
  bool _sceneReady = false;
  bool _initialized = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (_isWindows) {
      unawaited(_initializeWindows());
    } else {
      unawaited(_initializeMobile());
    }
  }

  Future<void> _initializeMobile() async {
    final controller = mobile.WebViewController();
    _mobileController = controller;
    try {
      await controller.setJavaScriptMode(mobile.JavaScriptMode.unrestricted);
      await controller.addJavaScriptChannel(
        'AirspaceBridge',
        onMessageReceived: (message) => _receiveMessage(message.message),
      );
      await controller.setNavigationDelegate(
        mobile.NavigationDelegate(
          onPageStarted: (_) {
            final backendBaseUrl = widget.backendBaseUrl;
            if (backendBaseUrl == null || backendBaseUrl.isEmpty) return;
            // Navigation starts before the bundled module script executes.
            unawaited(controller.runJavaScript(
              'window.AIRSPACE_API_BASE = ${jsonEncode(backendBaseUrl)};',
            ));
          },
        ),
      );
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) widget.onCommandSenderReady(_sendCommand);
      });
      await controller.loadFlutterAsset(airspaceSceneAssetKey);
      if (mounted) setState(() => _initialized = true);
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _initializeWindows() async {
    final controller = windows.WebviewController();
    _windowsController = controller;
    try {
      await controller.initialize();
      _windowsMessageSubscription = controller.webMessage.listen(
        _receiveMessage,
        onError: _showError,
      );
      final backendBaseUrl = widget.backendBaseUrl;
      if (backendBaseUrl != null && backendBaseUrl.isNotEmpty) {
        await controller.addScriptToExecuteOnDocumentCreated(
          'window.AIRSPACE_API_BASE = ${jsonEncode(backendBaseUrl)};',
        );
      }

      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      _assetServer = server;
      server.listen((request) => unawaited(_serveSceneAsset(request)));
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) widget.onCommandSenderReady(_sendCommand);
      });
      await controller.loadUrl(
        'http://127.0.0.1:${server.port}/scene/index.html',
      );
      if (mounted) setState(() => _initialized = true);
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _serveSceneAsset(HttpRequest request) async {
    final segments = request.uri.pathSegments
        .where((segment) => segment.isNotEmpty)
        .toList();
    if (segments.isEmpty || segments.first != 'scene') {
      request.response.statusCode = HttpStatus.notFound;
      await request.response.close();
      return;
    }
    final fileSegments = segments.skip(1).toList();
    if (fileSegments.any(
      (segment) =>
          segment == '.' ||
          segment == '..' ||
          segment.contains('/') ||
          segment.contains(r'\'),
    )) {
      request.response.statusCode = HttpStatus.badRequest;
      await request.response.close();
      return;
    }

    final relativePath =
        fileSegments.isEmpty ? 'index.html' : fileSegments.join('/');
    final assetKey = 'assets/flight-map-3d/dist/build/$relativePath';
    try {
      final data = await rootBundle.load(assetKey);
      request.response.headers.contentType = _contentType(relativePath);
      request.response.headers.set(HttpHeaders.cacheControlHeader, 'no-store');
      request.response.add(
        data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes),
      );
      await request.response.close();
    } catch (_) {
      request.response.statusCode = HttpStatus.notFound;
      await request.response.close();
    }
  }

  ContentType _contentType(String path) {
    final extension = path.split('.').last.toLowerCase();
    const mimeTypes = {
      'html': 'text/html; charset=utf-8',
      'js': 'text/javascript; charset=utf-8',
      'mjs': 'text/javascript; charset=utf-8',
      'css': 'text/css; charset=utf-8',
      'json': 'application/json; charset=utf-8',
      'svg': 'image/svg+xml',
      'png': 'image/png',
      'jpg': 'image/jpeg',
      'jpeg': 'image/jpeg',
      'webp': 'image/webp',
      'glb': 'model/gltf-binary',
      'gltf': 'model/gltf+json',
    };
    return ContentType.parse(
      mimeTypes[extension] ?? 'application/octet-stream',
    );
  }

  void _receiveMessage(Object? rawMessage) {
    final event = parseSceneEvent(rawMessage);
    if (event == null || !mounted) return;
    if (event['event'] == 'ready') {
      _sceneReady = true;
      final queued = List<Map<String, Object?>>.of(_pendingCommands);
      _pendingCommands.clear();
      for (final command in queued) {
        _queueDispatch(command);
      }
    }
    widget.onSceneEvent(event);
  }

  void _sendCommand(Map<String, Object?> command) {
    if (!_sceneReady) {
      _pendingCommands.add(command);
      return;
    }
    _queueDispatch(command);
  }

  void _queueDispatch(Map<String, Object?> command) {
    _commandQueue = _commandQueue.then((_) => _dispatchCommand(command));
  }

  Future<void> _dispatchCommand(Map<String, Object?> command) async {
    final script =
        'window.AirspaceThree.receiveMessage(${jsonEncode(command)});';
    try {
      if (_isWindows) {
        await _windowsController?.executeScript(script);
      } else {
        await _mobileController?.runJavaScript(script);
      }
    } catch (error) {
      _showError(error);
    }
  }

  void _showError(Object error) {
    if (!mounted) return;
    setState(() {
      _error = 'Unable to load the packaged 3D scene: $error';
      _initialized = true;
    });
  }

  @override
  void dispose() {
    unawaited(_windowsMessageSubscription?.cancel());
    final server = _assetServer;
    if (server != null) unawaited(server.close(force: true));
    final controller = _windowsController;
    if (controller != null) unawaited(controller.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Text(
            _error!,
            style: const TextStyle(color: Colors.white70),
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    if (!_initialized) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_isWindows) {
      final controller = _windowsController;
      if (controller == null) {
        return const Center(child: CircularProgressIndicator());
      }
      return windows.Webview(controller);
    }
    final controller = _mobileController;
    if (controller == null) {
      return const Center(child: CircularProgressIndicator());
    }
    return mobile.WebViewWidget(controller: controller);
  }
}
