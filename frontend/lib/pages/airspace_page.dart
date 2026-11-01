import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:pointer_interceptor/pointer_interceptor.dart';

import '../models/airspace_models.dart';
import '../services/airspace_bridge_service.dart';
import '../services/webview_host.dart';
import '../widgets/aircraft_status_card.dart';
import '../widgets/metrics_panel.dart';
import '../widgets/pressure_legend.dart';
import '../widgets/route_point_sheet.dart';
import '../widgets/scenario_selector.dart';

class AirspacePage extends StatefulWidget {
  final String sceneUrl;

  const AirspacePage({super.key, required this.sceneUrl});

  @override
  State<AirspacePage> createState() => _AirspacePageState();
}

class _AirspacePageState extends State<AirspacePage> {
  /// Mirrors the scene's SCENARIOS registry (src/main.js). Hardcoded so
  /// the dropdown is populated IMMEDIATELY — never empty, never dependent
  /// on the bridge arriving.
  static const List<ScenarioInfo> _knownScenarios = [
    ScenarioInfo(id: 'crossroads-storm', title: 'Storm crossroads — 3 aircraft'),
    ScenarioInfo(id: 'converge-bucharest', title: 'Converge on Bucharest — 4 aircraft'),
    ScenarioInfo(id: 'carpathian-siege', title: 'Carpathian siege — triangle flights'),
    ScenarioInfo(id: 'storm-wall', title: 'Storm wall'),
    ScenarioInfo(id: 'over-the-top', title: 'Over the top'),
    ScenarioInfo(id: 'low-corridor', title: 'Low corridor'),
    ScenarioInfo(id: 'slalom', title: 'Slalom'),
    ScenarioInfo(id: 'fuel-critical', title: 'Fuel critical'),
    ScenarioInfo(id: 'in-flight-replan', title: 'In-flight replan'),
    ScenarioInfo(id: 'real-meteo', title: 'Real meteo (AIFS)'),
  ];

  final _bridge = AirspaceBridgeService();
  late final AirspaceWebviewHost _host;
  StreamSubscription<AirspaceEvent>? _subscription;
  Timer? _watchdog;
  Timer? _scenarioConfirmTimer;

  List<ScenarioInfo> _scenarios = _knownScenarios;
  String _selectedScenario = _knownScenarios.first.id;
  String _statusText = 'Initializing…';
  ScenarioLoadedPayload? _payload;
  FlightState? _flightState;
  bool _sceneReady = false;
  bool _sceneConnected = false;
  String? _loadError;
  int _selectedFlight = 0;

  @override
  void initState() {
    super.initState();
    _host = AirspaceWebviewHost(_bridge);
    _subscription = _bridge.events.listen(_onEvent);

    _watchdog = Timer(const Duration(seconds: 20), () {
      if (!mounted || _sceneReady) return;
      setState(() {
        _loadError = _sceneConnected
            ? 'Scene connected but no scenario loaded.\n'
              'Is the backend running on port 8000?'
            : 'Scene did not respond at:\n${widget.sceneUrl}\n\n'
              'Is the Vite dev server running in assets/flight-map-3d?';
      });
    });
  }

  void _onEvent(AirspaceEvent event) {
    switch (event) {
      case AirspaceReady():
        debugPrint('[bridge] ready — ${event.scenarios.length} scenarios from scene');
        setState(() {
          if (event.scenarios.isNotEmpty) _scenarios = event.scenarios;
          _sceneConnected = true;
          _statusText = 'Scene connected — loading scenario…';
        });
      case AirspaceStatus():
        setState(() {
          _statusText = event.text;
          _sceneConnected = true;
        });
      case AirspaceScenarioLoaded():
        _watchdog?.cancel();
        _scenarioConfirmTimer?.cancel();
        debugPrint('[bridge] scenario loaded: ${event.payload.scenario}');
        setState(() {
          _payload = event.payload;
          _selectedScenario = event.payload.scenario;
          _sceneReady = true;
          _loadError = null;
          _selectedFlight = 0;
        });
      case AirspaceFlightStateEvent():
        setState(() => _flightState = event.state);
      case AirspaceFlightSelected():
        setState(() => _selectedFlight = event.index);
      case AirspaceRoutePointEvent():
        _showRoutePoint(event.info);
      case AirspaceRoutePointCleared():
        Navigator.of(context, rootNavigator: true).maybePop();
      case AirspaceWeatherUpdated():
        setState(() => _statusText = event.trajectoryStatus);
      case AirspaceErrorEvent():
        debugPrint('[bridge] error: ${event.message}');
        setState(() => _statusText = 'Error: ${event.message}');
    }
  }

  void _selectScenario(String id) {
    debugPrint('[bridge] -> select scenario $id');
    setState(() {
      _selectedScenario = id;
      _statusText = 'Loading $id…';
    });
    _host.loadScenario(id);

    // Failsafe: if the scene does not confirm within 4 s, reload the
    // iframe with ?scenario=<id> — the scene reads that at boot.
    _scenarioConfirmTimer?.cancel();
    _scenarioConfirmTimer = Timer(const Duration(seconds: 4), () {
      if (!mounted) return;
      if (_selectedScenario == id && _payload?.scenario != id) {
        debugPrint('[bridge] no confirm for $id — reloading scene via URL param');
        _host.reloadWithScenario(id);
      }
    });
  }

  void _showRoutePoint(RoutePointInfo info) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (_) => RoutePointSheet(info: info),
    );
  }

  @override
  void dispose() {
    _watchdog?.cancel();
    _scenarioConfirmTimer?.cancel();
    _subscription?.cancel();
    _bridge.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isPhone = MediaQuery.of(context).size.width < 760;

    return Scaffold(
      backgroundColor: const Color(0xFF05080E),
      body: SafeArea(
        child: Stack(
          children: [
            Positioned.fill(child: _host.buildView(widget.sceneUrl)),

            // Loading / error overlay — shielded so the iframe can't eat
            // taps while it's up.
            if (!_sceneReady)
              Positioned.fill(
                child: PointerInterceptor(
                  child: Container(
                    color: const Color(0xFF05080E),
                    alignment: Alignment.center,
                    padding: const EdgeInsets.symmetric(horizontal: 32),
                    child: _loadError != null
                        ? Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.cloud_off,
                                  color: Color(0xFFE2836F), size: 36),
                              const SizedBox(height: 14),
                              Text(
                                _loadError!,
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                    fontSize: 12.5,
                                    color: Color(0xFF8FA3B5),
                                    height: 1.6),
                              ),
                            ],
                          )
                        : Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Text(
                                'AIRSPACE',
                                style: TextStyle(
                                    fontSize: 30,
                                    fontWeight: FontWeight.w200,
                                    letterSpacing: 8,
                                    color: Color(0xFFE9EEF4)),
                              ),
                              const SizedBox(height: 14),
                              Text(_statusText,
                                  style: const TextStyle(
                                      fontSize: 11,
                                      color: Color(0xFF8FA3B5))),
                              const SizedBox(height: 14),
                              const SizedBox(
                                width: 180,
                                child: LinearProgressIndicator(
                                  minHeight: 2,
                                  color: Color(0xFFE3B563),
                                  backgroundColor: Color(0x14FFFFFF),
                                ),
                              ),
                            ],
                          ),
                  ),
                ),
              ),

            // Top bar: status + scenario selector — shielded.
            Positioned(
              top: 10,
              left: 10,
              right: 10,
              child: PointerInterceptor(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 8),
                        decoration: BoxDecoration(
                          color: const Color(0xB80D141E),
                          borderRadius: BorderRadius.circular(10),
                          border:
                              Border.all(color: const Color(0x17FFFFFF)),
                        ),
                        child: Row(
                          children: [
                            Container(
                              width: 6,
                              height: 6,
                              decoration: const BoxDecoration(
                                color: Color(0xFF6FD6A0),
                                shape: BoxShape.circle,
                                boxShadow: [
                                  BoxShadow(
                                      color: Color(0xFF6FD6A0), blurRadius: 8)
                                ],
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                _statusLine,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    fontSize: 11, color: Color(0xFF8FA3B5)),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    SizedBox(
                      width: isPhone ? 220 : 264,
                      child: ScenarioSelector(
                        scenarios: _scenarios,
                        selected: _selectedScenario,
                        onSelected: _selectScenario,
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Right: metrics + legend — shielded.
            Positioned(
              top: isPhone ? 210 : 96,
              right: 10,
              child: PointerInterceptor(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    if (_payload != null)
                      MetricsPanel(
                        baseline: _payload!.baseline,
                        optimized: _payload!.optimized,
                      ),
                    const SizedBox(height: 12),
                    if (_payload != null)
                      PressureLegend(levels: _payload!.legend),
                  ],
                ),
              ),
            ),

            // Bottom-left: aircraft status card — shielded.
            if (_flightState != null)
              Positioned(
                left: 10,
                bottom: 10,
                child: PointerInterceptor(
                  child: AircraftStatusCard(
                    state: _flightState!,
                    aircraft:
                        _payload?.aircraft ?? const AircraftProfileInfo(),
                    flightCount: _payload?.flightCount ?? 1,
                    flights: _payload?.flights ?? const [],
                    selectedIndex: _selectedFlight,
                    onSelectFlight: (index) => _host.selectFlight(index),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  String get _statusLine {
    final payload = _payload;
    if (payload == null) return _statusText;
    final parts = <String>[
      payload.source,
      if (payload.eventCount > 0) '${payload.eventCount} weather events',
      if (payload.trajectoryStatus != null) payload.trajectoryStatus!,
    ];
    return parts.join('  ·  ');
  }
}