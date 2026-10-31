import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';
import '../models/models.dart';
import '../util/format.dart';
import '../util/polling.dart';
import '../widgets/common.dart';
import '../widgets/transit_map.dart';

class PassengerScreen extends StatefulWidget {
  const PassengerScreen({super.key});

  @override
  State<PassengerScreen> createState() => _PassengerScreenState();
}

class _PassengerScreenState extends PollingState<PassengerScreen> {
  List<RouteInfo>? _routes;
  String? _routesError;

  RouteInfo? _route;
  DirectionBrief? _direction;
  DirectionDetail? _detail;
  String? _detailError;
  StopPoint? _stop;

  Arrivals? _arrivals;
  String? _arrivalsError;
  DateTime? _lastOk;

  final TextEditingController _searchCtl = TextEditingController();
  Timer? _debounce;
  List<StopSearchResult>? _results;
  String? _searchError;

  String _sessionId = '';
  final Set<int> _sending = <int>{};

  @override
  bool get pollingEnabled => _detail != null && _stop != null;

  @override
  void initState() {
    super.initState();
    _init();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchCtl.dispose();
    super.dispose();
  }

  Future<void> _init() async {
    await _loadSession();
    await _loadRoutes();
  }

  /// Anonim sessiya identifikatoru (hesab deyil). Server onu yalnız hash kimi saxlayır.
  Future<void> _loadSession() async {
    final valid = RegExp(r'^[A-Za-z0-9_-]{16,64}$');
    String? id;
    SharedPreferences? prefs;
    try {
      prefs = await SharedPreferences.getInstance();
      id = prefs.getString('session_id');
    } catch (_) {
      prefs = null;
    }
    if (id == null || !valid.hasMatch(id)) {
      final rnd = Random.secure();
      id = List<String>.generate(32, (_) => rnd.nextInt(16).toRadixString(16)).join();
      try {
        await prefs?.setString('session_id', id);
      } catch (_) {
        // yaddaşa yazılmadısa: bu sessiya üçün yaddaşda qalır
      }
    }
    _sessionId = id;
  }

  Future<void> _loadRoutes() async {
    setState(() {
      _routes = null;
      _routesError = null;
    });
    try {
      final routes = await api.routes();
      if (!mounted) return;
      setState(() => _routes = routes);
      if (routes.isNotEmpty && routes.first.directions.isNotEmpty) {
        await _selectDirection(routes.first, routes.first.directions.first);
      }
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _routesError = e.message);
    }
  }

  Future<void> _selectDirection(RouteInfo route, DirectionBrief dir, {String? stopId}) async {
    setState(() {
      _route = route;
      _direction = dir;
      _detail = null;
      _detailError = null;
      _stop = null;
      _arrivals = null;
      _arrivalsError = null;
    });
    syncPolling();
    try {
      final d = await api.direction(dir.id);
      if (!mounted || _direction?.id != dir.id) return;
      StopPoint? chosen;
      if (stopId != null) {
        for (final s in d.stops) {
          if (s.stopId == stopId) chosen = s;
        }
      }
      // Standart seçim: sona yaxın dayanacaq (bir neçə avtobus hələ yaxınlaşır)
      chosen ??= d.stops.isEmpty ? null : d.stops[max(0, d.stops.length - 3)];
      setState(() {
        _detail = d;
        _stop = chosen;
      });
      syncPolling();
      await poll();
    } on ApiException catch (e) {
      if (!mounted || _direction?.id != dir.id) return;
      setState(() => _detailError = e.message);
    }
  }

  void _selectStop(StopPoint s) {
    setState(() {
      _stop = s;
      _arrivals = null;
      _arrivalsError = null;
    });
    syncPolling();
    poll();
  }

  @override
  Future<void> poll() async {
    final dir = _direction;
    final stop = _stop;
    if (dir == null || stop == null || _detail == null) return;
    try {
      final a = await api.arrivals(dir.id, stop.stopId);
      if (!mounted || _direction?.id != dir.id || _stop?.stopId != stop.stopId) return;
      setState(() {
        _arrivals = a;
        _arrivalsError = null;
        _lastOk = DateTime.now();
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _arrivalsError = e.message);
    }
  }

  void _onSearchChanged(String q) {
    _debounce?.cancel();
    final text = q.trim();
    if (text.length < 2) {
      setState(() {
        _results = null;
        _searchError = null;
      });
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 400), () => _search(text));
  }

  Future<void> _search(String q) async {
    try {
      final r = await api.searchStops(q);
      if (!mounted || _searchCtl.text.trim() != q) return;
      setState(() {
        _results = r;
        _searchError = null;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _searchError = e.message);
    }
  }

  void _pickSearchResult(StopSearchResult r) {
    if (r.servedBy.isEmpty) {
      _snack('«${r.name}» real dayanacaqdır, lakin demo xətlərdən heç birində yoxdur.');
      return;
    }
    final target = r.servedBy.first;
    for (final route in _routes ?? <RouteInfo>[]) {
      for (final d in route.directions) {
        if (d.id == target.directionId) {
          _searchCtl.clear();
          setState(() {
            _results = null;
          });
          _selectDirection(route, d, stopId: r.stopId);
          return;
        }
      }
    }
  }

  Future<void> _report(BusView bus, String level) async {
    if (_sending.contains(bus.id) || _sessionId.isEmpty) return;
    setState(() => _sending.add(bus.id));
    try {
      await api.report(busId: bus.id, level: level, sessionId: _sessionId);
      _snack('Bildiriş qəbul edildi: ${bus.code} — ${crowdLabel(level)}');
      await poll();
    } on ApiException catch (e) {
      if (e.status == 429) {
        _snack('Eyni avtobusa ${e.retryAfterSeconds ?? 60} saniyə sonra yenidən bildirə bilərsiniz.');
      } else {
        _snack(e.message);
      }
    } finally {
      if (mounted) setState(() => _sending.remove(bus.id));
    }
  }

  void _snack(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(text)));
  }

  // ------------------------------------------------------------------ UI

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Sərnişin')),
      body: _body(),
    );
  }

  Widget _body() {
    if (_routesError != null) return ErrorView(message: _routesError!, onRetry: _loadRoutes);
    final routes = _routes;
    if (routes == null) return const LoadingView(message: 'Marşrutlar yüklənir...');
    if (routes.isEmpty) {
      return const EmptyView(
        message: 'Demo marşrut yoxdur.\nServerdə "import-stops" və "seed-demo" əmrlərini işlədin (README).',
        icon: Icons.alt_route,
      );
    }
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: ListView(
          padding: const EdgeInsets.all(12),
          children: [
            const DemoBanner(
              'Dayanacaqlar REAL; "Demo" marşrutlar sxematik xətdir (real yol deyil), avtobus GPS-i SİMULYASİYADIR. '
              'ETA real yol üzrə dəqiq vaxt vədi deyil.',
            ),
            const SizedBox(height: 10),
            _selectors(routes),
            const SizedBox(height: 8),
            _searchBox(),
            const SizedBox(height: 8),
            ..._mapAndArrivals(),
          ],
        ),
      ),
    );
  }

  Widget _selectors(List<RouteInfo> routes) {
    final detail = _detail;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Marşrut', style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Wrap(
              spacing: 8,
              children: [
                for (final r in routes)
                  ChoiceChip(
                    label: Text('${r.name} (demo)'),
                    selected: _route?.id == r.id,
                    onSelected: (_) {
                      if (r.directions.isNotEmpty) _selectDirection(r, r.directions.first);
                    },
                  ),
              ],
            ),
            const SizedBox(height: 10),
            const Text('İstiqamət', style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Wrap(
              spacing: 8,
              children: [
                for (final d in _route?.directions ?? <DirectionBrief>[])
                  ChoiceChip(
                    label: Text(d.name),
                    selected: _direction?.id == d.id,
                    onSelected: (_) => _selectDirection(_route!, d),
                  ),
              ],
            ),
            const SizedBox(height: 10),
            const Text('Dayanacaq', style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            if (_detailError != null)
              ErrorView(message: _detailError!, onRetry: () => _selectDirection(_route!, _direction!))
            else if (detail == null)
              const LinearProgressIndicator()
            else
              InputDecorator(
                decoration: const InputDecoration(border: OutlineInputBorder(), contentPadding: EdgeInsets.symmetric(horizontal: 10)),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    isExpanded: true,
                    value: _stop?.stopId,
                    items: [
                      for (final s in detail.stops)
                        DropdownMenuItem<String>(
                          value: s.stopId,
                          child: Text('${s.seq + 1}. ${s.name}', overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: (v) {
                      if (v == null) return;
                      for (final s in detail.stops) {
                        if (s.stopId == v) _selectStop(s);
                      }
                    },
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _searchBox() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: _searchCtl,
              onChanged: _onSearchChanged,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                labelText: 'Dayanacağı adla axtar (real dayanacaqlar)',
                border: OutlineInputBorder(),
              ),
            ),
            if (_searchError != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_searchError!, style: const TextStyle(color: Color(0xFFC62828)))),
            if (_results != null && _results!.isEmpty)
              const Padding(padding: EdgeInsets.only(top: 8), child: Text('Heç nə tapılmadı.')),
            if (_results != null)
              for (final r in _results!.take(6))
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.directions_bus_filled_outlined),
                  title: Text(r.name),
                  subtitle: Text(
                    r.servedBy.isEmpty
                        ? 'Kod ${r.stopId} · demo xətlərdə yoxdur'
                        : 'Kod ${r.stopId} · ${r.servedBy.first.routeName} (demo), ${r.servedBy.first.directionName}',
                  ),
                  onTap: () => _pickSearchResult(r),
                ),
          ],
        ),
      ),
    );
  }

  List<Widget> _mapAndArrivals() {
    final detail = _detail;
    final stop = _stop;
    if (detail == null || stop == null) return const [];
    final arrivals = _arrivals;
    final out = <Widget>[];

    out.add(
      SizedBox(
        height: 270,
        child: TransitMap(
          key: ValueKey<int>(detail.id),
          lines: [MapLine(detail.polyline, const Color(0xFF0B5FA5))],
          stops: [for (final s in detail.stops) MapStop(s.point, selected: s.seq == stop.seq)],
          buses: [
            for (final b in arrivals?.buses ?? <BusView>[])
              if (b.point != null) MapBus(b.point!, b.code, b.crowd.level, dimmed: b.status == 'offline' || b.status == 'passed'),
          ],
        ),
      ),
    );
    out.add(
      const Padding(
        padding: EdgeInsets.symmetric(vertical: 4),
        child: Text('Mavi xətt: sxematik demo xətti (real yol deyil). Avtobuslar: simulyasiya.', style: TextStyle(fontSize: 11.5, color: Color(0xFF616161))),
      ),
    );

    if (_arrivalsError != null) {
      out.add(StaleBanner(message: _arrivalsError!, lastOk: _lastOk, onRetry: poll));
    }
    if (arrivals == null) {
      if (_arrivalsError == null) out.add(const LoadingView(message: 'Avtobuslar yüklənir...'));
      return out;
    }

    out.add(
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Text('«${arrivals.stopName}» dayanacağına gələn avtobuslar', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
      ),
    );

    final alt = arrivals.alternative;
    if (alt != null) out.add(_alternativeCard(alt));

    final upcoming = arrivals.buses.where((b) => b.status == 'approaching' || b.status == 'at_stop' || b.status == 'stopped').toList();
    final others = arrivals.buses.where((b) => !upcoming.contains(b)).toList();

    if (upcoming.isEmpty) {
      out.add(const EmptyView(message: 'Hazırda bu dayanacağa yaxınlaşan avtobus yoxdur.', icon: Icons.directions_bus_outlined));
    }
    for (final b in upcoming) {
      out.add(_busCard(b));
    }
    if (others.isNotEmpty) {
      out.add(const Padding(
        padding: EdgeInsets.only(top: 10, bottom: 4),
        child: Text('Dayanacağı artıq keçən / siqnalı olmayan avtobuslar', style: TextStyle(fontWeight: FontWeight.w700)),
      ));
      for (final b in others) {
        out.add(_busCard(b));
      }
    }
    out.add(Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Text(arrivals.etaNote, style: const TextStyle(fontSize: 11.5, color: Color(0xFF616161))),
    ));
    return out;
  }

  Widget _alternativeCard(Alternative alt) {
    return Card(
      color: const Color(0xFFE8F5E9),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.swap_horiz, color: Color(0xFF2E7D32)),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Növbəti avtobus daha boş ola bilər: ${alt.busCode} (${fmtEta(alt.etaSeconds)}, '
                '${fmtDuration(alt.extraWaitSeconds)} sonra) — ${crowdLabel(alt.level)}. '
                'İlk avtobus ${alt.firstBus}: ${crowdLabel(alt.firstLevel)}.\n'
                'Bildirişlər: ${alt.reportsCount}, son yenilənmə: ${fmtAge(alt.dataAgeSeconds)}. Bu, sərnişin bildirişlərinə əsaslanan təxmindir.',
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _busCard(BusView b) {
    final muted = b.status == 'passed' || b.status == 'offline';
    final canReport = b.status != 'offline';
    final sending = _sending.contains(b.id);
    return Card(
      color: muted ? const Color(0xFFF5F5F5) : null,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.directions_bus),
                const SizedBox(width: 8),
                Text(b.code, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
                const SizedBox(width: 8),
                if (b.isSimulated) const Tag('SİMULYASİYA'),
                const Spacer(),
                if (b.status == 'approaching' || b.status == 'at_stop')
                  Text(fmtEta(b.etaSeconds), style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
              ],
            ),
            const SizedBox(height: 4),
            Text(_statusLine(b)),
            const SizedBox(height: 8),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CrowdChip(level: b.crowd.level),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    b.crowd.level == null
                        ? 'Son 5 dəqiqədə bildiriş yoxdur'
                        : 'Aktual bildiriş: ${b.crowd.reportsCount}'
                            '${b.crowd.demoReportsCount > 0 ? ' (${b.crowd.demoReportsCount} demo)' : ''}'
                            ' · son yenilənmə: ${fmtAge(b.crowd.latestAgeSeconds)}',
                    style: const TextStyle(fontSize: 12.5),
                  ),
                ),
              ],
            ),
            if (canReport) ...[
              const SizedBox(height: 10),
              const Text('Bu avtobusda sıxlıq necədir?', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
              const SizedBox(height: 6),
              Row(
                children: [
                  for (final lvl in const ['LOW', 'MEDIUM', 'HIGH']) ...[
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: sending ? null : () => _report(b, lvl),
                        icon: Icon(crowdIcon(lvl), size: 18, color: crowdColor(lvl)),
                        label: Text(crowdLabel(lvl)),
                        style: OutlinedButton.styleFrom(
                          side: BorderSide(color: crowdColor(lvl)),
                          foregroundColor: crowdColor(lvl),
                          padding: const EdgeInsets.symmetric(horizontal: 4),
                        ),
                      ),
                    ),
                    if (lvl != 'HIGH') const SizedBox(width: 6),
                  ],
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _statusLine(BusView b) {
    final parts = <String>[busStatusLabel(b.status)];
    if (b.distanceToStopM != null && (b.status == 'approaching' || b.status == 'stopped')) {
      parts.add('dayanacağa ~${b.distanceToStopM} m');
    }
    if (b.status == 'stopped') parts.add('ETA məlum deyil');
    if (b.gpsAgeSeconds != null) parts.add('GPS: ${fmtAge(b.gpsAgeSeconds)}');
    return parts.join(' · ');
  }
}
