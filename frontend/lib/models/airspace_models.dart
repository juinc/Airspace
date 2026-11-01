/// Typed models for the Flutter <-> Three.js bridge.
/// Every field is null-safe: the UI renders "—" for null values.
/// Units contract: km, km/h, m/s, hPa, kg, minutes (see BRIDGE_PROTOCOL.md).
library;

class ScenarioInfo {
  final String id;
  final String title;
  const ScenarioInfo({required this.id, required this.title});

  factory ScenarioInfo.fromJson(Map<String, dynamic> json) => ScenarioInfo(
        id: json['id'] as String? ?? '',
        title: json['title'] as String? ?? json['id'] as String? ?? '',
      );
}

/// One aircraft in a multi-flight scenario.
class FlightInfo {
  final String id;
  final String? origin;
  final String? destination;
  const FlightInfo({required this.id, this.origin, this.destination});

  factory FlightInfo.fromJson(Map<String, dynamic> json) => FlightInfo(
        id: json['id'] as String? ?? '',
        origin: json['origin'] as String?,
        destination: json['destination'] as String?,
      );
}

class RouteMetrics {
  final double? distanceKm;
  final double? timeMin;
  final double? avgExposure;
  final double? fuelEstimatedKg;
  final double? initialFuelKg;

  const RouteMetrics({
    this.distanceKm,
    this.timeMin,
    this.avgExposure,
    this.fuelEstimatedKg,
    this.initialFuelKg,
  });

  factory RouteMetrics.fromJson(Map<String, dynamic>? json) => RouteMetrics(
        distanceKm: _toDouble(json?['distance_km']),
        timeMin: _toDouble(json?['time_min']),
        avgExposure: _toDouble(json?['avg_exposure']),
        fuelEstimatedKg: _toDouble(json?['fuel_estimated_kg']),
        initialFuelKg: _toDouble(json?['initial_fuel_kg']),
      );
}

class PressureLevelInfo {
  final String pressure;
  final double altitudeKm;
  final int colorValue;
  const PressureLevelInfo({
    required this.pressure,
    required this.altitudeKm,
    required this.colorValue,
  });

  factory PressureLevelInfo.fromJson(Map<String, dynamic> json) =>
      PressureLevelInfo(
        pressure: json['pressure'] as String? ?? '',
        altitudeKm: _toDouble(json['altitude_km']) ?? 0,
        colorValue: _parseColor(json['color'] as String? ?? '#6fd3e8'),
      );
}

class AircraftProfileInfo {
  final String? name;
  final double? weightKg;
  final double? maxRampWeightKg;
  final double? maxTakeoffWeightKg;
  final double? maxLandingWeightKg;
  final double? fuelCapacityKg;
  final double? maxCruiseSpeedKts;
  final double? cruiseSpeedKmh;
  final int? serviceCeilingFt;
  final int? maxRangeNm;

  const AircraftProfileInfo({
    this.name,
    this.weightKg,
    this.maxRampWeightKg,
    this.maxTakeoffWeightKg,
    this.maxLandingWeightKg,
    this.fuelCapacityKg,
    this.maxCruiseSpeedKts,
    this.cruiseSpeedKmh,
    this.serviceCeilingFt,
    this.maxRangeNm,
  });

  factory AircraftProfileInfo.fromJson(Map<String, dynamic>? json) =>
      AircraftProfileInfo(
        name: json?['aircraft_name'] as String?,
        weightKg: _toDouble(json?['weight_kg']),
        maxRampWeightKg: _toDouble(json?['max_ramp_weight_kg']),
        maxTakeoffWeightKg: _toDouble(json?['max_takeoff_weight_kg']),
        maxLandingWeightKg: _toDouble(json?['max_landing_weight_kg']),
        fuelCapacityKg: _toDouble(json?['fuel_capacity_kg']),
        maxCruiseSpeedKts: _toDouble(json?['max_cruise_speed_kts']),
        cruiseSpeedKmh: _toDouble(json?['cruise_speed_kmh']),
        serviceCeilingFt: json?['service_ceiling_ft'] as int?,
        maxRangeNm: json?['max_range_nm'] as int?,
      );
}

/// Full payload of `airspace:scenario-loaded` — drives every static panel.
class ScenarioLoadedPayload {
  final String scenario;
  final String title;
  final String source;
  final String? fetchedAt;
  final String? trajectoryStatus;
  final int eventCount;
  final RouteMetrics baseline;
  final RouteMetrics optimized;
  final AircraftProfileInfo aircraft;
  final List<PressureLevelInfo> legend;
  final List<FlightInfo> flights;
  final int flightCount;

  const ScenarioLoadedPayload({
    required this.scenario,
    required this.title,
    required this.source,
    this.fetchedAt,
    this.trajectoryStatus,
    required this.eventCount,
    required this.baseline,
    required this.optimized,
    required this.aircraft,
    required this.legend,
    required this.flights,
    required this.flightCount,
  });

  factory ScenarioLoadedPayload.fromJson(Map<String, dynamic> json) {
    final meta = _map(json['meta']);
    final metrics = _map(json['metrics']);
    final assumptions = _map(json['routing_assumptions']);
    return ScenarioLoadedPayload(
      scenario: json['scenario'] as String? ?? '',
      title: json['title'] as String? ?? '',
      source: (meta['source'] as String? ?? 'unknown').toUpperCase(),
      fetchedAt: meta['fetched_at'] as String?,
      trajectoryStatus: meta['trajectory_status'] as String?,
      eventCount: meta['event_count'] as int? ?? 0,
      baseline: RouteMetrics.fromJson(_map(metrics['baseline'])),
      optimized: RouteMetrics.fromJson(_map(metrics['optimized'])),
      aircraft: AircraftProfileInfo.fromJson(_map(assumptions['aircraft_profile'])),
      legend: (json['legend'] as List<dynamic>? ?? [])
          .map((e) => PressureLevelInfo.fromJson(_map(e)))
          .toList(),
      flights: (json['flights'] as List<dynamic>? ?? [])
          .map((e) => FlightInfo.fromJson(_map(e)))
          .toList(),
      flightCount: json['flight_count'] as int? ?? 1,
    );
  }
}

/// Live payload of `airspace:flight-state` at 10 Hz — drives the status card.
class FlightState {
  final int flightIndex;
  final String? flightId;
  final double progress;
  final String phase;
  final double lat;
  final double lon;
  final double altitudeKm;
  final double verticalSpeedMS;
  final double groundSpeedKmh;
  final double? exposureScore;
  final int? fuelRemainingKg;
  final int? fuelPercent;
  final int? burnRateKgPerH;
  final double? etaMin;
  final double? distanceRemainingKm;

  const FlightState({
    required this.flightIndex,
    this.flightId,
    required this.progress,
    required this.phase,
    required this.lat,
    required this.lon,
    required this.altitudeKm,
    required this.verticalSpeedMS,
    required this.groundSpeedKmh,
    this.exposureScore,
    this.fuelRemainingKg,
    this.fuelPercent,
    this.burnRateKgPerH,
    this.etaMin,
    this.distanceRemainingKm,
  });

  factory FlightState.fromJson(Map<String, dynamic> json) => FlightState(
        flightIndex: json['flight_index'] as int? ?? 0,
        flightId: json['flight_id'] as String?,
        progress: _toDouble(json['progress']) ?? 0,
        phase: json['phase'] as String? ?? 'CRUISE',
        lat: _toDouble(json['lat']) ?? 0,
        lon: _toDouble(json['lon']) ?? 0,
        altitudeKm: _toDouble(json['altitude_km']) ?? 0,
        verticalSpeedMS: _toDouble(json['vertical_speed_m_per_s']) ?? 0,
        groundSpeedKmh: _toDouble(json['ground_speed_kmh']) ?? 0,
        exposureScore: _toDouble(json['exposure_score']),
        fuelRemainingKg: json['fuel_remaining_kg'] as int?,
        fuelPercent: json['fuel_percent'] as int?,
        burnRateKgPerH: json['burn_rate_kg_per_h'] as int?,
        etaMin: _toDouble(json['eta_min']),
        distanceRemainingKm: _toDouble(json['distance_remaining_km']),
      );
}

/// Payload of `airspace:route-point` — the tap-to-inspect coordinates card.
class RoutePointInfo {
  final String route;
  final double lat;
  final double lon;
  final double altitudeKm;
  final double? routeProgress;
  final int? pressureLevel;
  final double? exposureScore;
  final String? phase;
  final int? fuelRemainingKg;
  final double? temperature;
  final double? windSpeed;
  final double? windDirection;
  final double? relativeHumidity;
  final double? cloudCover;
  final double? precipitation;
  final double? cape;

  const RoutePointInfo({
    required this.route,
    required this.lat,
    required this.lon,
    required this.altitudeKm,
    this.routeProgress,
    this.pressureLevel,
    this.exposureScore,
    this.phase,
    this.fuelRemainingKg,
    this.temperature,
    this.windSpeed,
    this.windDirection,
    this.relativeHumidity,
    this.cloudCover,
    this.precipitation,
    this.cape,
  });

  factory RoutePointInfo.fromJson(Map<String, dynamic> json) {
    final weather = _map(json['weather']);
    return RoutePointInfo(
      route: json['route'] as String? ?? 'route',
      lat: _toDouble(json['lat']) ?? 0,
      lon: _toDouble(json['lon']) ?? 0,
      altitudeKm: _toDouble(json['altitude_km']) ?? 0,
      routeProgress: _toDouble(json['route_progress']),
      pressureLevel: json['pressure_level'] as int?,
      exposureScore: _toDouble(json['exposure_score']),
      phase: json['phase'] as String?,
      fuelRemainingKg: json['fuel_remaining_kg'] as int?,
      temperature: _toDouble(weather['temperature']),
      windSpeed: _toDouble(weather['wind_speed']),
      windDirection: _toDouble(weather['wind_direction']),
      relativeHumidity: _toDouble(weather['relative_humidity']),
      cloudCover: _toDouble(weather['cloud_cover']),
      precipitation: _toDouble(weather['precipitation']),
      cape: _toDouble(weather['cape']),
    );
  }
}

double? _toDouble(dynamic value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value);
  return null;
}

Map<String, dynamic> _map(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

int _parseColor(String hex) {
  final cleaned = hex.replaceFirst('#', '');
  if (cleaned.length == 6) {
    return int.tryParse('FF$cleaned', radix: 16) ?? 0xFF6FD3E8;
  }
  return 0xFF6FD3E8;
}