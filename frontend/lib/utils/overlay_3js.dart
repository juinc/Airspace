import 'package:flutter/material.dart';
import 'package:frontend/airspace_protocol.dart';
import 'package:frontend/three_view.dart';
import 'package:frontend/utils/overlay_elements/air_title.dart';
import 'package:frontend/utils/overlay_elements/plane_info.dart';
import 'package:frontend/utils/overlay_elements/travel_info.dart';

class Overlay3js extends StatefulWidget {
  const Overlay3js({super.key});

  @override
  State<Overlay3js> createState() => _Overlay3jsState();
}

class _Overlay3jsState extends State<Overlay3js> {
  static const _layerNames = ['weather', 'routes', 'airports', 'altitude'];

  late String? _backendBaseUrl;
  final Map<String, bool> _layerVisibility = {
    for (final layer in _layerNames) layer: true,
  };
  final Map<String, Map<String, Object?>> _telemetry = {};
  final Map<String, Map<String, Object?>> _flightMetrics = {};
  final List<String> _scenarioFlightIds = [];

  List<Map<String, String>> _scenarios = [];
  Map<String, Object?> _scenarioMeta = {};
  Object? _eventCount;
  Object? _pressureLevels;
  Map<String, Object?>? _generalMetrics;
  Map<String, Object?>? _coordinate;
  String? _selectedScenario;
  String _status = 'Waiting for the 3D scene…';
  SceneCommandSender? _sendSceneCommand;
  bool _sceneReady = false;
  bool _initialScenarioRequested = false;
  bool _hasScenarioData = false;
  bool _apiBaseCommandSent = false;

  @override
  void initState() {
    super.initState();
    const configuredBase = String.fromEnvironment('AIRSPACE_API_BASE');
    final trimmedBase = configuredBase.trim();
    _backendBaseUrl =
        trimmedBase.isNotEmpty ? normalizeApiBaseUrl(trimmedBase) : null;
  }

  void _onSceneCommandSenderReady(SceneCommandSender sender) {
    _sendSceneCommand = sender;
    _sendConfiguredApiBaseIfNeeded();
    if (_hasScenarioData) _syncLayerVisibility();
    _loadInitialScenarioIfNeeded();
  }

  void _sendConfiguredApiBaseIfNeeded() {
    final baseUrl = _backendBaseUrl;
    if (!_sceneReady ||
        _apiBaseCommandSent ||
        baseUrl == null ||
        baseUrl.isEmpty) {
      return;
    }
    _sendSceneCommand?.call(setApiBaseCommand(baseUrl));
    _apiBaseCommandSent = _sendSceneCommand != null;
  }

  void _onSceneEvent(Map<String, Object?> event) {
    final eventName = event['event'];
    setState(() {
      if (eventName == 'ready') {
        _sceneReady = true;
        final scenarios = event['scenarios'];
        if (scenarios is List) {
          _scenarios = scenarios
              .whereType<Map>()
              .map(_scenarioFromMap)
              .whereType<Map<String, String>>()
              .toList();
        }
        final initialScenario = event['initialScenario'];
        if (initialScenario is String) _selectedScenario = initialScenario;
        _status = 'Scene ready';
      } else if (eventName == 'status') {
        final message = event['message'];
        if (message is String) _status = message;
        final scenario = event['scenario'];
        if (scenario is String) _selectedScenario = scenario;
      } else if (eventName == 'scenarioLoaded') {
        _hasScenarioData = true;
        final scenario = event['scenario'];
        if (scenario is String) {
          _selectedScenario = scenario;
          _status = 'Loaded $scenario';
        }
        _scenarioMeta = _stringKeyedMap(event['meta']);
        _eventCount = event['eventCount'];
        _pressureLevels = event['pressureLevels'];
        _scenarioFlightIds
          ..clear()
          ..addAll(_extractFlightIds(event['flights']));
        _flightMetrics
          ..clear()
          ..addAll(_extractFlightMetrics(
            event['flights'],
            _stringKeyedMap(event['metrics']),
          ));
        _generalMetrics = _flightMetrics.isEmpty
            ? _stringKeyedMap(event['metrics'])
            : null;
        _coordinate = null;
        _telemetry.clear();
      } else if (eventName == 'telemetry') {
        final flightId = event['flightId'];
        if (flightId is String && flightId.isNotEmpty) {
          _telemetry[flightId] = event;
        }
      } else if (eventName == 'coordinateClick') {
        _coordinate = event;
      } else if (eventName == 'coordinateCleared') {
        _coordinate = null;
      } else if (eventName == 'error') {
        final message = event['message'];
        if (message is String) _status = message;
        final scenario = event['scenario'];
        if (scenario is String) _selectedScenario = scenario;
      }
    });
    if (eventName == 'ready') {
      _sendConfiguredApiBaseIfNeeded();
      _loadInitialScenarioIfNeeded();
    } else if (eventName == 'scenarioLoaded') {
      _syncLayerVisibility();
    }
  }

  void _loadInitialScenarioIfNeeded() {
    final sender = _sendSceneCommand;
    final scenario = _selectedScenario;
    if (!_sceneReady ||
        _initialScenarioRequested ||
        sender == null ||
        scenario == null) {
      return;
    }
    _initialScenarioRequested = true;
    setState(() => _status = 'Loading $scenario…');
    sender(loadScenarioCommand(scenario));
  }

  void _syncLayerVisibility() {
    final sender = _sendSceneCommand;
    if (!_sceneReady || sender == null) return;
    for (final layer in _layerNames) {
      sender(toggleLayerCommand(layer, _layerVisibility[layer] ?? true));
    }
  }

  Map<String, String>? _scenarioFromMap(Map value) {
    final id = value['id'];
    final title = value['title'];
    if (id is! String || id.isEmpty) return null;
    return {
      'id': id,
      'title': title is String && title.isNotEmpty ? title : id,
    };
  }

  List<String> _extractFlightIds(Object? flights) {
    if (flights is! List) return [];
    final ids = <String>[];
    for (final flight in flights) {
      if (flight is String && flight.isNotEmpty) {
        ids.add(flight);
      } else if (flight is Map && flight['flightId'] is String) {
        ids.add(flight['flightId'] as String);
      } else if (flight is Map && flight['id'] is String) {
        ids.add(flight['id'] as String);
      }
    }
    return ids;
  }

  Map<String, Map<String, Object?>> _extractFlightMetrics(
    Object? flights,
    Map<String, Object?> fallbackMetrics,
  ) {
    if (flights is! List) return {};
    final result = <String, Map<String, Object?>>{};
    for (var index = 0; index < flights.length; index++) {
      final flight = flights[index];
      if (flight is! Map) continue;
      var metrics = _stringKeyedMap(flight['metrics']);
      if (metrics.isEmpty && index == 0) metrics = fallbackMetrics;
      if (metrics.isEmpty) continue;
      final flightId = flight['flightId'];
      final id = flight['id'];
      final label = flightId is String && flightId.isNotEmpty
          ? flightId
          : id is String && id.isNotEmpty
              ? id
              : 'Flight ${index + 1}';
      result[label] = metrics;
    }
    return result;
  }

  Map<String, Object?> _stringKeyedMap(Object? value) {
    if (value is! Map) return {};
    final result = <String, Object?>{};
    for (final entry in value.entries) {
      if (entry.key is String) result[entry.key as String] = entry.value;
    }
    return result;
  }

  void _sendCommand(Map<String, Object?> command) {
    final sender = _sendSceneCommand;
    if (sender == null) return;
    sender(command);
  }

  void _selectScenario(String scenario) {
    setState(() {
      _selectedScenario = scenario;
      _status = 'Loading $scenario…';
      _hasScenarioData = false;
      _coordinate = null;
      _eventCount = null;
      _pressureLevels = null;
      _scenarioFlightIds.clear();
      _telemetry.clear();
      _flightMetrics.clear();
      _generalMetrics = null;
      _scenarioMeta = {};
    });
    _sendCommand(loadScenarioCommand(scenario));
  }

  void _reloadScenario() {
    final scenario = _selectedScenario;
    if (scenario == null) return;
    _selectScenario(scenario);
  }

  void _setLayerVisible(String layer, bool visible) {
    setState(() => _layerVisibility[layer] = visible);
    _sendCommand(toggleLayerCommand(layer, visible));
  }

  Future<void> _configureApiBase() async {
    final controller = TextEditingController(text: _backendBaseUrl ?? '');
    final entered = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1E222B),
        title: const Text(
          'Backend address',
          style: TextStyle(color: Colors.white),
        ),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: TextInputType.url,
          style: const TextStyle(color: Colors.white),
          decoration: const InputDecoration(
            hintText: 'http://192.168.1.20:8000',
            helperText:
                'Use a reachable host. Android emulator: 10.0.2.2:8000; '
                'for a physical device enter the computer’s LAN address. '
                'Use HTTPS on iOS unless local HTTP is allowed by ATS.',
            helperMaxLines: 3,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('Apply'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (entered == null) return;

    final normalized = normalizeApiBaseUrl(entered);
    if (normalized == null) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Enter a root URL such as http://192.168.1.20:8000.'),
        ),
      );
      return;
    }
    if (!mounted) return;
    setState(() {
      _backendBaseUrl = normalized;
      _apiBaseCommandSent = false;
      _status =
          'Backend address updated. Reload the selected scenario to use it.';
    });
    if (_sceneReady) _sendConfiguredApiBaseIfNeeded();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth >= 1000) {
            return Row(
              children: [
                SizedBox(width: 274, child: _buildControlPanel()),
                Expanded(child: _buildScene()),
                SizedBox(width: 306, child: _buildDetailsPanel()),
              ],
            );
          }

          final compactHeight = constraints.maxHeight;
          final toolbarHeight =
              (compactHeight * 0.30).clamp(128.0, 184.0).toDouble();
          final detailsHeight =
              (compactHeight * 0.30).clamp(132.0, 210.0).toDouble();
          return Column(
            children: [
              SizedBox(height: toolbarHeight, child: _buildCompactToolbar()),
              Expanded(child: _buildScene()),
              SizedBox(height: detailsHeight, child: _buildCompactDetails()),
            ],
          );
        },
      ),
    );
  }

  Widget _buildScene() => ThreeView(
        onSceneEvent: _onSceneEvent,
        onCommandSenderReady: _onSceneCommandSenderReady,
        backendBaseUrl: _backendBaseUrl,
      );

  Widget _buildControlPanel() {
    return Container(
      color: const Color(0xFF14171C),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const AirTitle(),
            const SizedBox(height: 18),
            _statusCard(),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(child: _scenarioControl()),
                IconButton(
                  tooltip: 'Reload selected scenario',
                  onPressed: _sceneReady && _selectedScenario != null
                      ? _reloadScenario
                      : null,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
            const SizedBox(height: 16),
            _cameraControls(),
            const SizedBox(height: 16),
            _layerControls(),
            const SizedBox(height: 12),
            _apiBaseButton(),
          ],
        ),
      ),
    );
  }

  Widget _buildCompactToolbar() {
    return Container(
      width: double.infinity,
      color: const Color(0xFF14171C),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      child: SingleChildScrollView(
        child: Column(
          children: [
            Row(
              children: [
                const Icon(Icons.flight, color: Color(0xFFFFE306), size: 19),
                const SizedBox(width: 8),
                const Text(
                  'AIRSPACE',
                  style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1.4,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    _status,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.65),
                      fontSize: 11,
                    ),
                  ),
                ),
                IconButton(
                  tooltip: 'Configure backend address',
                  visualDensity: VisualDensity.compact,
                  onPressed: _configureApiBase,
                  icon: const Icon(Icons.settings_ethernet, size: 19),
                  color: const Color(0xFFFFE306),
                ),
              ],
            ),
            Row(
              children: [
                Expanded(child: _scenarioControl(compact: true)),
                IconButton(
                  tooltip: 'Reload selected scenario',
                  visualDensity: VisualDensity.compact,
                  onPressed: _sceneReady && _selectedScenario != null
                      ? _reloadScenario
                      : null,
                  icon: const Icon(Icons.refresh, size: 19),
                ),
              ],
            ),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _cameraButton('Overview', 'overview'),
                  _cameraButton('Top down', 'topDown'),
                  const SizedBox(width: 8),
                  ..._layerNames.map(_layerChip),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _statusCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF1E222B),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            _sceneReady ? Icons.check_circle_outline : Icons.hourglass_top,
            color: _sceneReady ? const Color(0xFF64C895) : Colors.white54,
            size: 17,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              _status,
              style: const TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  Widget _scenarioControl({bool compact = false}) {
    final selectedExists =
        _scenarios.any((scenario) => scenario['id'] == _selectedScenario);
    return DropdownButtonFormField<String>(
      value: selectedExists ? _selectedScenario : null,
      isExpanded: true,
      decoration: InputDecoration(
        labelText: compact ? null : 'Weather scenario',
        hintText: _sceneReady ? 'Choose scenario' : 'Waiting for scene…',
        isDense: true,
        filled: true,
        fillColor: const Color(0xFF1E222B),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
      ),
      items: _scenarios
          .map(
            (scenario) => DropdownMenuItem<String>(
              value: scenario['id'],
              child: Text(
                scenario['title']!,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          )
          .toList(),
      onChanged: _sceneReady && _sendSceneCommand != null
          ? (value) {
              if (value != null) _selectScenario(value);
            }
          : null,
    );
  }

  Widget _cameraControls() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _sectionTitle('CAMERA'),
        const SizedBox(height: 6),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            _cameraButton('Overview', 'overview'),
            _cameraButton('Top down', 'topDown'),
          ],
        ),
      ],
    );
  }

  Widget _cameraButton(String label, String preset) => OutlinedButton(
        onPressed: _sceneReady && _sendSceneCommand != null
            ? () => _sendCommand(setCameraCommand(preset))
            : null,
        style: OutlinedButton.styleFrom(
          visualDensity: VisualDensity.compact,
          foregroundColor: Colors.white,
          side: BorderSide(color: Colors.white.withValues(alpha: 0.16)),
        ),
        child: Text(label),
      );

  Widget _layerControls() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _sectionTitle('LAYERS'),
        const SizedBox(height: 6),
        Wrap(
          spacing: 4,
          runSpacing: 2,
          children: _layerNames.map(_layerChip).toList(),
        ),
      ],
    );
  }

  Widget _layerChip(String layer) => FilterChip(
        label: Text(_titleCase(layer)),
        selected: _layerVisibility[layer] ?? true,
        visualDensity: VisualDensity.compact,
        onSelected: _sceneReady && _sendSceneCommand != null
            ? (visible) => _setLayerVisible(layer, visible)
            : null,
      );

  Widget _apiBaseButton() {
    final base = _backendBaseUrl;
    return OutlinedButton.icon(
      onPressed: _configureApiBase,
      icon: const Icon(Icons.settings_ethernet, size: 17),
      label: Flexible(
        child: Text(
          base ?? 'Backend: scene default',
          overflow: TextOverflow.ellipsis,
        ),
      ),
      style: OutlinedButton.styleFrom(
        foregroundColor: Colors.white70,
        alignment: Alignment.centerLeft,
      ),
    );
  }

  Widget _buildDetailsPanel() {
    return Container(
      color: const Color(0xFF14171C),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(14),
        child: Column(
          children: [
            _scenarioSummaryCard(),
            const SizedBox(height: 10),
            _metricsCard(),
            const SizedBox(height: 10),
            TravelInfo(coordinate: _coordinate),
            const SizedBox(height: 10),
            PlaneInfo(
              profile: _stringKeyedMap(_scenarioMeta['aircraftProfile']),
              telemetry: _telemetry,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCompactDetails() {
    return Container(
      color: const Color(0xFF14171C),
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 8),
        children: [
          SizedBox(
            width: 300,
            child: SingleChildScrollView(child: _scenarioSummaryCard()),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 300,
            child: SingleChildScrollView(child: _metricsCard()),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 300,
            child: SingleChildScrollView(
              child: TravelInfo(coordinate: _coordinate),
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 300,
            child: SingleChildScrollView(
              child: PlaneInfo(
                profile: _stringKeyedMap(_scenarioMeta['aircraftProfile']),
                telemetry: _telemetry,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _scenarioSummaryCard() {
    final fields = <(String, String)>[];
    if (_eventCount != null) {
      fields.add(('Weather events', _eventCount.toString()));
    }
    fields.addAll(_flattenValues(_pressureLevels, prefix: 'Pressure levels'));
    if (_scenarioFlightIds.isNotEmpty) {
      fields.add(('Flights', _scenarioFlightIds.join(', ')));
    }
    fields.addAll(_flattenValues(_scenarioMeta, prefix: 'Meta'));
    return _DataCard(
      title: 'SCENARIO STATUS',
      fields: fields,
      emptyMessage: 'Waiting for scenario data.',
    );
  }

  Widget _metricsCard() {
    final fields = <(String, String)>[];
    for (final entry in _flightMetrics.entries) {
      fields.addAll(_flattenValues(entry.value, prefix: entry.key));
    }
    final general = _generalMetrics;
    if (general != null) fields.addAll(_flattenValues(general));
    return _DataCard(
      title: 'FLIGHT METRICS',
      fields: fields,
      emptyMessage: 'No metrics reported.',
    );
  }

  Widget _sectionTitle(String title) => Text(
        title,
        style: TextStyle(
          color: Colors.white.withValues(alpha: 0.5),
          fontSize: 10,
          fontWeight: FontWeight.w800,
          letterSpacing: 1.3,
        ),
      );

  String _titleCase(String value) =>
      value[0].toUpperCase() + value.substring(1);
}

List<(String, String)> _flattenValues(
  Object? value, {
  String prefix = '',
}) {
  final fields = <(String, String)>[];

  void visit(Object? current, String path) {
    if (current == null) return;
    if (current is Map) {
      for (final entry in current.entries) {
        if (entry.key is! String) continue;
        final key = entry.key as String;
        visit(entry.value, path.isEmpty ? key : '$path · $key');
      }
      return;
    }
    if (current is List) {
      for (var index = 0; index < current.length; index++) {
        visit(current[index], '$path [$index]');
      }
      return;
    }
    fields.add((path.isEmpty ? 'Value' : path, current.toString()));
  }

  visit(value, prefix);
  return fields;
}

class _DataCard extends StatelessWidget {
  const _DataCard({
    required this.title,
    required this.fields,
    required this.emptyMessage,
  });

  final String title;
  final List<(String, String)> fields;
  final String emptyMessage;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1A).withValues(alpha: 0.88),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: Color(0xFFFFE306),
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.3,
            ),
          ),
          const SizedBox(height: 8),
          if (fields.isEmpty)
            Text(
              emptyMessage,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.55),
                fontSize: 12,
              ),
            )
          else
            ...fields.map(
              (field) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        field.$1,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.6),
                          fontSize: 11,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Flexible(
                      child: Text(
                        field.$2,
                        textAlign: TextAlign.right,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
