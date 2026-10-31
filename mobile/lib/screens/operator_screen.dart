import 'dart:math';

import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../models/models.dart';
import '../util/format.dart';
import '../util/polling.dart';
import '../widgets/common.dart';
import '../widgets/transit_map.dart';

class OperatorScreen extends StatefulWidget {
  const OperatorScreen({super.key});

  @override
  State<OperatorScreen> createState() => _OperatorScreenState();
}

class _OperatorScreenState extends PollingState<OperatorScreen> {
  int _tab = 0;

  OperatorOverview? _overview;
  List<AlertInfo>? _alerts;
  String? _error;
  DateTime? _lastOk;
  final Map<int, DirectionDetail> _geometry = <int, DirectionDetail>{};

  String _alertFilter = 'ACTIVE'; // ACTIVE | RESOLVED | ALL

  DemoStatus? _demo;
  String? _demoError;
  bool _demoBusy = false;

  @override
  Future<void> poll() async {
    try {
      final ov = await api.overview();
      final al = await api.alerts();
      for (final d in ov.directions) {
        if (_geometry.containsKey(d.directionId)) continue;
        try {
          _geometry[d.directionId] = await api.direction(d.directionId);
        } on ApiException {
          // xəritə xətti sonrakı yenilənmədə yenidən cəhd edilir
        }
      }
      if (!mounted) return;
      setState(() {
        _overview = ov;
        _alerts = al;
        _error = null;
        _lastOk = DateTime.now();
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  Future<void> _loadDemo() async {
    try {
      final s = await api.demoStatus();
      if (!mounted) return;
      setState(() {
        _demo = s;
        _demoError = null;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _demoError = e.status == 404 ? 'Demo idarəetməsi serverdə söndürülüb.' : e.message);
    }
  }

  Future<void> _runDemo(Future<void> Function() action, String okMessage) async {
    setState(() => _demoBusy = true);
    try {
      await action();
      if (!mounted) return;
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(okMessage)));
      await _loadDemo();
      await poll();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _demoBusy = false);
    }
  }

  Future<void> _confirmAndRun(String title, String body, Future<void> Function() action, String okMessage) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: Text(body),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Ləğv et')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text('Tətbiq et')),
        ],
      ),
    );
    if (ok == true) await _runDemo(action, okMessage);
  }

  // ------------------------------------------------------------------ UI

  @override
  Widget build(BuildContext context) {
    final activeCount = _overview?.activeAlertsCount ?? 0;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Operator paneli'),
        actions: [
          if (_lastOk != null)
            Center(
              child: Padding(
                padding: const EdgeInsets.only(right: 4),
                child: Text('Yeniləndi ${fmtClock(_lastOk!)}', style: const TextStyle(fontSize: 12)),
              ),
            ),
          IconButton(tooltip: 'İndi yenilə', onPressed: poll, icon: const Icon(Icons.refresh)),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) {
          setState(() => _tab = i);
          if (i == 2 && _demo == null) _loadDemo();
        },
        destinations: [
          const NavigationDestination(icon: Icon(Icons.alt_route), label: 'Xətlər'),
          NavigationDestination(
            icon: Badge(isLabelVisible: activeCount > 0, label: Text('$activeCount'), child: const Icon(Icons.warning_amber)),
            label: 'Xəbərdarlıqlar',
          ),
          const NavigationDestination(icon: Icon(Icons.science_outlined), label: 'Demo'),
        ],
      ),
      body: _body(),
    );
  }

  Widget _body() {
    final ov = _overview;
    if (ov == null) {
      if (_error != null) return ErrorView(message: _error!, onRetry: poll);
      return const LoadingView(message: 'Operator məlumatı yüklənir...');
    }
    final Widget content;
    switch (_tab) {
      case 0:
        content = _linesTab(ov);
        break;
      case 1:
        content = _alertsTab();
        break;
      default:
        content = _demoTab();
    }
    return Column(
      children: [
        if (_error != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: StaleBanner(message: _error!, lastOk: _lastOk, onRetry: poll),
          ),
        Expanded(child: content),
      ],
    );
  }

  // ---- Xətlər

  Widget _linesTab(OperatorOverview ov) {
    if (ov.directions.isEmpty) {
      return const EmptyView(
        message: 'Demo xətt yoxdur.\nServerdə "import-stops" və "seed-demo" əmrlərini işlədin (README).',
        icon: Icons.alt_route,
      );
    }
    final palette = <Color>[const Color(0xFF0B5FA5), const Color(0xFF6A1B9A), const Color(0xFF00796B), const Color(0xFFEF6C00)];
    final lines = <MapLine>[];
    final buses = <MapBus>[];
    for (var i = 0; i < ov.directions.length; i++) {
      final d = ov.directions[i];
      final g = _geometry[d.directionId];
      if (g != null) lines.add(MapLine(g.polyline, palette[i % palette.length]));
      for (final b in d.buses) {
        if (b.point != null) buses.add(MapBus(b.point!, b.code, b.crowd.level, dimmed: b.status == 'offline'));
      }
    }
    final map = TransitMap(key: const ValueKey<String>('operator-map'), lines: lines, stops: const [], buses: buses);
    final cards = <Widget>[
      DemoBanner(
        'DEMO: avtobuslar və GPS simulyasiyadır; xətlər sxematikdir. ${ov.rulesNote}',
      ),
      const SizedBox(height: 8),
      for (final d in ov.directions) _directionCard(d),
    ];

    return LayoutBuilder(
      builder: (context, c) {
        final wide = c.maxWidth >= 900;
        final list = ListView(padding: const EdgeInsets.all(12), children: cards);
        if (wide) {
          return Row(
            children: [
              Expanded(flex: 5, child: Padding(padding: const EdgeInsets.all(12), child: map)),
              Expanded(flex: 4, child: list),
            ],
          );
        }
        return Column(
          children: [
            SizedBox(height: 230, child: Padding(padding: const EdgeInsets.fromLTRB(12, 8, 12, 0), child: map)),
            Expanded(child: list),
          ],
        );
      },
    );
  }

  Widget _directionCard(OperatorDirection d) {
    final crowd = d.crowd;
    final ratio = crowd.highThresholdSeconds == 0 ? 0.0 : min(1.0, crowd.highForSeconds / crowd.highThresholdSeconds);
    final iv = d.intervals;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('${d.routeName} · ${d.directionName}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
                ),
                const Tag('DEMO'),
                if (d.activeAlertIds.isNotEmpty) ...[
                  const SizedBox(width: 6),
                  Chip(
                    visualDensity: VisualDensity.compact,
                    backgroundColor: const Color(0xFFFFEBEE),
                    label: Text('${d.activeAlertIds.length} xəbərdarlıq', style: const TextStyle(color: Color(0xFFC62828), fontWeight: FontWeight.w700)),
                  ),
                ],
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                CrowdChip(level: crowd.level),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    crowd.level == null ? noResultReason(crowd.reasonNoResult) : 'Orta bal: ${crowd.score} (1=aşağı, 3=yüksək)',
                    style: const TextStyle(fontSize: 12.5),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              'Məlumat əhatəsi: ${crowd.busesWithData}/${crowd.activeBuses} aktiv avtobus · '
              'son bildiriş: ${fmtAge(crowd.latestReportAgeSeconds)}',
              style: const TextStyle(fontSize: 12.5),
            ),
            Text('Aktiv avtobus: ${d.activeBuses}', style: const TextStyle(fontSize: 12.5)),
            if (crowd.highForSeconds > 0) ...[
              const SizedBox(height: 8),
              LinearProgressIndicator(value: ratio, minHeight: 8, color: const Color(0xFFC62828), backgroundColor: const Color(0xFFEEEEEE)),
              const SizedBox(height: 4),
              Text(
                'Aktual məlumatla fasiləsiz yüksək sıxlıq: ${fmtDuration(crowd.highForSeconds)} / ${fmtDuration(crowd.highThresholdSeconds)}',
                style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
              ),
            ],
            const Divider(height: 20),
            Text('Hədəf interval: ${fmtDuration(d.targetIntervalSeconds)}', style: const TextStyle(fontSize: 12.5)),
            Text(
              iv.medianS == null
                  ? 'Müşahidə olunan interval: kifayət qədər məlumat yoxdur'
                  : 'Müşahidə olunan interval: median ${fmtDuration(iv.medianS!)} (min ${fmtDuration(iv.minS ?? 0)} – maks ${fmtDuration(iv.maxS ?? 0)}, ${iv.samples} ölçmə)',
              style: const TextStyle(fontSize: 12.5),
            ),
            if (d.bunchingDetected)
              const Padding(
                padding: EdgeInsets.only(top: 4),
                child: Text('⚠ Avtobusların qruplaşması ehtimalı müşahidə olunur', style: TextStyle(fontSize: 12.5, color: Color(0xFFB26A00), fontWeight: FontWeight.w700)),
              ),
            if (d.diagnosis != 'unclear' && (crowd.level == 'HIGH' || d.bunchingDetected))
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('Ehtimal: ${diagnosisLabel(d.diagnosis)}', style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
              ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final b in d.buses)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: crowdBackground(b.crowd.level),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: crowdColor(b.crowd.level)),
                    ),
                    child: Text(
                      '${b.code.replaceFirst('DEMO-', '')} · ${crowdLabel(b.crowd.level)}${b.status == 'stopped' ? ' · dayanıb' : ''}${b.status == 'offline' ? ' · siqnal yox' : ''}',
                      style: TextStyle(fontSize: 12, color: crowdColor(b.crowd.level), fontWeight: FontWeight.w600),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  // ---- Xəbərdarlıqlar

  Widget _alertsTab() {
    final all = _alerts;
    if (all == null) return const LoadingView();
    final shown = all.where((a) => _alertFilter == 'ALL' || a.status == _alertFilter).toList();
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        SegmentedButton<String>(
          segments: const [
            ButtonSegment<String>(value: 'ACTIVE', label: Text('Aktiv')),
            ButtonSegment<String>(value: 'RESOLVED', label: Text('Həll olunmuş')),
            ButtonSegment<String>(value: 'ALL', label: Text('Hamısı')),
          ],
          selected: <String>{_alertFilter},
          onSelectionChanged: (s) => setState(() => _alertFilter = s.first),
        ),
        const SizedBox(height: 10),
        if (shown.isEmpty)
          const EmptyView(message: 'Bu filtr üzrə xəbərdarlıq yoxdur.', icon: Icons.check_circle_outline),
        for (final a in shown) _alertCard(a),
      ],
    );
  }

  Widget _alertCard(AlertInfo a) {
    final color = a.active ? const Color(0xFFC62828) : const Color(0xFF2E7D32);
    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: color, width: 1.4),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 6,
              runSpacing: 4,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Tag(a.active ? 'AKTİV' : 'HƏLL OLUNUB', color: color),
                if (a.isDemo) const Tag('DEMO'),
                Text(alertKindLabel(a.kind), style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
              ],
            ),
            const SizedBox(height: 8),
            Text(a.title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: 2),
            Text(
              'Yaranma: ${fmtClock(a.createdAt)}'
              '${a.resolvedAt != null ? ' · Həll olunub: ${fmtClock(a.resolvedAt!)}' : ''}',
              style: const TextStyle(fontSize: 12, color: Color(0xFF616161)),
            ),
            const SizedBox(height: 10),
            _section('Hadisə', Text(a.event)),
            _section('Mümkün səbəb', Text(a.possibleCause)),
            _section(
              'Ölçülmüş sübut',
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final e in a.evidence.entries)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 3),
                      child: Text.rich(
                        TextSpan(
                          children: [
                            TextSpan(text: '${evidenceLabelOrKey(e.key)}: ', style: const TextStyle(fontWeight: FontWeight.w600)),
                            TextSpan(text: evidenceValue(e.value)),
                          ],
                        ),
                        style: const TextStyle(fontSize: 12.5),
                      ),
                    ),
                ],
              ),
            ),
            _section('Operatora tövsiyə', Text(a.recommendation, style: const TextStyle(fontWeight: FontWeight.w600))),
            Text('${a.routeName} · ${a.directionName}', style: const TextStyle(fontSize: 11.5, color: Color(0xFF616161))),
          ],
        ),
      ),
    );
  }

  Widget _section(String title, Widget body) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title.toUpperCase(), style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Color(0xFF455A64))),
          const SizedBox(height: 2),
          body,
        ],
      ),
    );
  }

  // ---- Demo idarəetməsi

  Widget _demoTab() {
    if (_demoError != null) return ErrorView(message: _demoError!, onRetry: _loadDemo);
    final s = _demo;
    if (s == null) return const LoadingView();
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        const DemoBanner(
          'DEMO İDARƏETMƏSİ — real əməliyyat deyil. Düymələr yalnız SİMULYASİYA məlumatını (GPS, demo bildirişləri, '
          'xəbərdarlıqlar) dəyişir. Real dayanacaqlar silinmir. Ssenarilər real analiz kodundan keçir; '
          '10 dəqiqəlik qayda qısaldılmır, ssenari əvvəlki ~11 dəqiqənin məlumatını yaradır.',
        ),
        const SizedBox(height: 8),
        Text('Real dayanacaq sayı: ${s.stopsLoaded} · Aktiv ssenari: ${s.activeScenario ?? '—'}'),
        const SizedBox(height: 8),
        if (!s.structureReady || s.stopsLoaded == 0)
          const StaleBanner(message: 'Demo hazır deyil: serverdə "import-stops" və "seed-demo" əmrlərini işlədin.'),
        for (final sc in s.scenarios)
          Card(
            color: sc.name == s.activeScenario ? const Color(0xFFE3F2FD) : null,
            child: ListTile(
              title: Text(sc.label, style: const TextStyle(fontWeight: FontWeight.w700)),
              subtitle: Text(sc.description),
              trailing: FilledButton.tonal(
                onPressed: _demoBusy
                    ? null
                    : () => _confirmAndRun(
                          'Ssenari: ${sc.label}',
                          'Mövcud simulyasiya GPS-i, bildirişlər və xəbərdarlıqlar silinib ssenari yenidən qurulacaq.',
                          () => api.applyScenario(sc.name),
                          'Ssenari tətbiq olundu: ${sc.label}',
                        ),
                child: const Text('Tətbiq et'),
              ),
            ),
          ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: _demoBusy
              ? null
              : () => _confirmAndRun(
                    'Demo sıfırlama',
                    'Simulyasiya məlumatı silinəcək və "Normal hərəkət" ssenarisi qurulacaq. Real dayanacaqlara toxunulmur.',
                    api.resetDemo,
                    'Demo sıfırlandı',
                  ),
          icon: const Icon(Icons.restart_alt),
          label: const Text('Demo sıfırla'),
        ),
        if (_demoBusy) const Padding(padding: EdgeInsets.only(top: 12), child: LinearProgressIndicator()),
      ],
    );
  }
}
