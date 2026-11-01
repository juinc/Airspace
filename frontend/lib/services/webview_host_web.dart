import 'dart:async';
import 'dart:convert';
import 'dart:html' as html;
import 'dart:ui_web' as ui_web;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import 'airspace_bridge_service.dart';

/// Web host (Chrome/Edge): the scene lives in an IFrameElement. The scene's
/// JS bridge posts every event to window.parent as a JSON string — parsed
/// here. Commands go back the same way (Dart Maps don't survive the
/// browser's structured clone).
class AirspaceWebviewHost {
  final AirspaceBridgeService bridge;
  html.IFrameElement? _iframe;
  StreamSubscription<html.MessageEvent>? _messageSubscription;
  bool _registered = false;
  String? _baseUrl;

  AirspaceWebviewHost(this.bridge) {
    // Registered in the CONSTRUCTOR, not buildView: this must exist before
    // the iframe ever loads, and must not depend on build being called.
    _messageSubscription = html.window.onMessage.listen(_onMessage);
  }

  void _onMessage(html.MessageEvent event) {
    final data = event.data;
    if (data is Map) {
      final map = Map<String, dynamic>.from(data);
      if ((map['type'] as String?)?.startsWith('airspace:') ?? false) {
        bridge.handleRawMessage(map);
      }
    } else if (data is String) {
      // Scene events arrive as JSON strings.
      try {
        final decoded = jsonDecode(data);
        if (decoded is Map<String, dynamic> &&
            (decoded['type'] as String?)?.startsWith('airspace:') == true) {
          bridge.handleRawMessage(decoded);
        }
      } catch (_) {
        // Not our message — ignore.
      }
    }
  }

  Widget buildView(String url) {
    _baseUrl = url;
    if (!_registered) {
      _registered = true;

      ui_web.platformViewRegistry.registerViewFactory(
        'airspace_scene',
        (int viewId) {
          final iframe = html.IFrameElement()
            ..src = url
            ..style.border = 'none'
            ..style.width = '100%'
            ..style.height = '100%'
            ..allow = 'fullscreen';
          _iframe = iframe;
          return iframe;
        },
      );
    }
    return const HtmlElementView(viewType: 'airspace_scene');
  }

  Future<void> dispatch(Map<String, dynamic> command) async {
    final frame = _iframe;
    if (frame == null) {
      debugPrint('[bridge] dispatch dropped — iframe not built yet');
      return;
    }
    frame.contentWindow?.postMessage(jsonEncode(command), '*');
  }

  /// Hard fallback: reload the iframe with ?scenario=<id>. The scene reads
  /// that at boot, so this works even if the command channel is broken.
  Future<void> reloadWithScenario(String id) async {
    final frame = _iframe;
    final base = _baseUrl;
    if (frame == null || base == null) return;
    final uri = Uri.parse(base);
    final query = Map<String, String>.from(uri.queryParameters)
      ..['scenario'] = id;
    frame.src = uri.replace(queryParameters: query).toString();
  }

  Future<void> loadScenario(String id, {double? routeProgress}) => dispatch({
        'type': 'airspace:loadScenario',
        'scenario': id,
        if (routeProgress != null) 'routeProgress': routeProgress,
      });

  Future<void> setCameraPreset(String preset) =>
      dispatch({'type': 'airspace:setCamera', 'preset': preset});

  Future<void> toggleLayer(String layer, bool visible) => dispatch(
      {'type': 'airspace:toggleLayer', 'layer': layer, 'visible': visible});

  Future<void> replanWeather() => dispatch({'type': 'airspace:replanWeather'});

  Future<void> clearSelection() =>
      dispatch({'type': 'airspace:clearSelection'});

  Future<void> selectFlight(int index) =>
      dispatch({'type': 'airspace:selectFlight', 'index': index});

  void dispose() {
    _messageSubscription?.cancel();
  }
}