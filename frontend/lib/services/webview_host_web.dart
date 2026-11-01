import 'dart:async';
import 'dart:convert';
import 'dart:html' as html;
import 'dart:ui_web' as ui_web;

import 'package:flutter/widgets.dart';

import 'airspace_bridge_service.dart';

/// Web host (Chrome/Edge): the scene lives in an IFrameElement. The scene's
/// JS bridge posts every event to window.parent — which is THIS window —
/// and listens for postMessage commands, so no extra JS glue is needed.
class AirspaceWebviewHost {
  final AirspaceBridgeService bridge;
  html.IFrameElement? _iframe;
  StreamSubscription<html.MessageEvent>? _messageSubscription;
  bool _registered = false;

  AirspaceWebviewHost(this.bridge);

  Widget buildView(String url) {
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

      // Every scene event arrives here (scene posts to window.parent).
      _messageSubscription = html.window.onMessage.listen((event) {
        final data = event.data;
        if (data is Map) {
          final map = Map<String, dynamic>.from(data);
          if ((map['type'] as String?)?.startsWith('airspace:') ?? false) {
            bridge.handleRawMessage(map);
          }
        } else if (data is String) {
          // Some browsers deliver structured objects as JSON strings.
          try {
            final decoded = jsonDecode(data);
            if (decoded is Map<String, dynamic> &&
                (decoded['type'] as String?)?.startsWith('airspace:') ==
                    true) {
              bridge.handleRawMessage(decoded);
            }
          } catch (_) {
            // Not our message — ignore.
          }
        }
      });
    }
    return const HtmlElementView(viewType: 'airspace_scene');
  }

  /// The scene listens for window 'message' events and dispatches them —
  /// so posting the command to the iframe is all we need.
  ///
  /// Commands are posted as JSON STRINGS: Dart Maps do not survive the
  /// browser's structured clone, so posting the Map directly arrived as
  /// an empty object and commands were silently dropped. The scene's
  /// bridge parses string payloads.
  Future<void> dispatch(Map<String, dynamic> command) async {
    _iframe?.contentWindow?.postMessage(jsonEncode(command), '*');
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
}