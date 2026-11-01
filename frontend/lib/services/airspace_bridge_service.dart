import 'dart:async';

import '../models/airspace_models.dart';

/// Typed event union delivered from the scene to Flutter.
sealed class AirspaceEvent {
  const AirspaceEvent();
}

class AirspaceReady extends AirspaceEvent {
  final List<ScenarioInfo> scenarios;
  final bool mobile;
  const AirspaceReady(this.scenarios, this.mobile);
}

class AirspaceStatus extends AirspaceEvent {
  final String text;
  const AirspaceStatus(this.text);
}

class AirspaceScenarioLoaded extends AirspaceEvent {
  final ScenarioLoadedPayload payload;
  const AirspaceScenarioLoaded(this.payload);
}

class AirspaceFlightStateEvent extends AirspaceEvent {
  final FlightState state;
  const AirspaceFlightStateEvent(this.state);
}

/// Emitted when a plane is clicked in the 3D scene — syncs Flutter's
/// selection chips with the scene's selected aircraft.
class AirspaceFlightSelected extends AirspaceEvent {
  final int index;
  final String? id;
  const AirspaceFlightSelected(this.index, this.id);
}

class AirspaceRoutePointEvent extends AirspaceEvent {
  final RoutePointInfo info;
  const AirspaceRoutePointEvent(this.info);
}

class AirspaceRoutePointCleared extends AirspaceEvent {
  const AirspaceRoutePointCleared();
}

class AirspaceWeatherUpdated extends AirspaceEvent {
  final int updateNumber;
  final bool replanned;
  final String trajectoryStatus;
  const AirspaceWeatherUpdated(
      this.updateNumber, this.replanned, this.trajectoryStatus);
}

class AirspaceErrorEvent extends AirspaceEvent {
  final String message;
  const AirspaceErrorEvent(this.message);
}

/// Platform-independent event stream. The WebView host (mobile or web)
/// feeds raw JSON messages in via handleRawMessage.
class AirspaceBridgeService {
  final _events = StreamController<AirspaceEvent>.broadcast();

  Stream<AirspaceEvent> get events => _events.stream;

  void handleRawMessage(Map<String, dynamic> json) {
    _events.add(_parse(json));
  }

  AirspaceEvent _parse(Map<String, dynamic> json) {
    switch (json['type'] as String? ?? '') {
      case 'airspace:ready':
        return AirspaceReady(
          (json['scenarios'] as List<dynamic>? ?? [])
              .map((e) => ScenarioInfo.fromJson(Map<String, dynamic>.from(e)))
              .toList(),
          json['mobile'] as bool? ?? false,
        );
      case 'airspace:status':
        return AirspaceStatus(json['text'] as String? ?? '');
      case 'airspace:scenario-loaded':
        return AirspaceScenarioLoaded(ScenarioLoadedPayload.fromJson(json));
      case 'airspace:flight-state':
        return AirspaceFlightStateEvent(FlightState.fromJson(json));
      case 'airspace:flight-selected':
        return AirspaceFlightSelected(
          json['index'] as int? ?? 0,
          json['id'] as String?,
        );
      case 'airspace:route-point':
        return AirspaceRoutePointEvent(RoutePointInfo.fromJson(json));
      case 'airspace:route-point-cleared':
        return const AirspaceRoutePointCleared();
      case 'airspace:weather-updated':
        return AirspaceWeatherUpdated(
          json['update_number'] as int? ?? 0,
          json['replanned'] as bool? ?? false,
          json['trajectory_status'] as String? ?? '',
        );
      case 'airspace:error':
        return AirspaceErrorEvent(
            json['message'] as String? ?? 'Unknown error');
      default:
        return AirspaceErrorEvent('Unknown bridge event: ${json['type']}');
    }
  }

  void dispose() {
    _events.close();
  }
}