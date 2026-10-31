import 'dart:async';

import 'package:flutter/widgets.dart';

import '../config.dart';

/// Bütün ekranlar üçün: yeniləmə YALNIZ ekran aktiv olduqda işləyir.
/// Dayanır: tətbiq arxa plana keçəndə, başqa ekran üstünə açılanda, ekran bağlananda.
final RouteObserver<Route<dynamic>> routeObserver = RouteObserver<Route<dynamic>>();

class ActivePoller with WidgetsBindingObserver {
  ActivePoller({required this.onTick, this.period = const Duration(seconds: AppConfig.pollSeconds)});

  final Future<void> Function() onTick;
  final Duration period;

  Timer? _timer;
  bool _enabled = false;
  bool _visible = true;
  bool _foreground = true;
  bool _busy = false;

  bool get running => _timer != null;

  void init() => WidgetsBinding.instance.addObserver(this);

  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    _timer = null;
  }

  set enabled(bool v) {
    _enabled = v;
    _refresh();
  }

  set visible(bool v) {
    _visible = v;
    _refresh();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    _refresh();
  }

  Future<void> _tick() async {
    if (_busy) return; // üst-üstə düşən sorğuların qarşısı
    _busy = true;
    try {
      await onTick();
    } finally {
      _busy = false;
    }
  }

  void _refresh() {
    final should = _enabled && _visible && _foreground;
    if (should && _timer == null) {
      _tick();
      _timer = Timer.periodic(period, (_) => _tick());
    } else if (!should && _timer != null) {
      _timer!.cancel();
      _timer = null;
    }
  }
}

/// Dövri yenilənən ekranların bazası. Alt sinif `poll()` və `pollingEnabled` təyin edir.
abstract class PollingState<T extends StatefulWidget> extends State<T> implements RouteAware {
  late final ActivePoller _poller = ActivePoller(onTick: poll);

  Future<void> poll();

  bool get pollingEnabled => true;

  void syncPolling() => _poller.enabled = pollingEnabled;

  @override
  void initState() {
    super.initState();
    _poller.init();
    syncPolling();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final route = ModalRoute.of(context);
    if (route != null) routeObserver.subscribe(this, route);
  }

  @override
  void dispose() {
    routeObserver.unsubscribe(this);
    _poller.dispose();
    super.dispose();
  }

  @override
  void didPush() {}

  @override
  void didPop() {}

  @override
  void didPopNext() => _poller.visible = true; // üstündəki ekran bağlandı

  @override
  void didPushNext() => _poller.visible = false; // üstünə başqa ekran açıldı
}
