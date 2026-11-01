import 'dart:async';
import 'dart:convert';
import 'dart:html' as html;
import 'dart:js_util' as js_util;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

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
  html.IFrameElement? _frame;
  StreamSubscription<html.MessageEvent>? _messageSubscription;
  final List<Map<String, Object?>> _pendingCommands = [];
  bool _sceneReady = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _messageSubscription = html.window.onMessage.listen(_receiveMessage);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) widget.onCommandSenderReady(_sendCommand);
    });
  }

  void _configureFrame(Object element) {
    final frame = element as html.IFrameElement;
    _frame = frame;
    frame
      ..setAttribute('width', '100%')
      ..setAttribute('height', '100%')
      ..setAttribute('allow', 'fullscreen')
      ..style.border = '0'
      ..style.width = '100%'
      ..style.height = '100%';
    unawaited(_loadPackagedScene(frame));
  }

  Future<void> _loadPackagedScene(html.IFrameElement frame) async {
    try {
      var document = await rootBundle.loadString(airspaceSceneAssetKey);
      final assetBase = Uri.base.resolve(
        'assets/assets/flight-map-3d/dist/build/',
      );
      final baseTag =
          '<base href="${const HtmlEscape().convert(assetBase.toString())}">';
      final backendBaseUrl = widget.backendBaseUrl;
      final backendScript = backendBaseUrl == null || backendBaseUrl.isEmpty
          ? ''
          : '<script>window.AIRSPACE_API_BASE = '
              '${jsonEncode(backendBaseUrl)};</script>';
      document = document.replaceFirstMapped(
        RegExp(r'<head[^>]*>', caseSensitive: false),
        (match) => '${match[0]}$baseTag$backendScript',
      );
      frame.setAttribute('srcdoc', document);
    } catch (error) {
      if (mounted) {
        setState(() => _error = 'Unable to load packaged scene: $error');
      }
    }
  }

  void _receiveMessage(html.MessageEvent event) {
    if (event.source != _frame?.contentWindow) return;
    final message = parseSceneEvent(js_util.dartify(event.data));
    if (message == null || !mounted) return;
    if (message['event'] == 'ready') {
      _sceneReady = true;
      final queued = List<Map<String, Object?>>.of(_pendingCommands);
      _pendingCommands.clear();
      for (final command in queued) {
        _dispatchCommand(command);
      }
    }
    widget.onSceneEvent(message);
  }

  void _sendCommand(Map<String, Object?> command) {
    if (!_sceneReady) {
      _pendingCommands.add(command);
      return;
    }
    _dispatchCommand(command);
  }

  void _dispatchCommand(Map<String, Object?> command) {
    _frame?.contentWindow?.postMessage(js_util.jsify(command), '*');
  }

  @override
  void dispose() {
    unawaited(_messageSubscription?.cancel());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        HtmlElementView.fromTagName(
          tagName: 'iframe',
          onElementCreated: _configureFrame,
        ),
        if (_error != null)
          ColoredBox(
            color: const Color(0xFF101216),
            child: Center(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Text(
                  _error!,
                  style: const TextStyle(color: Colors.white70),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
          ),
      ],
    );
  }
}
