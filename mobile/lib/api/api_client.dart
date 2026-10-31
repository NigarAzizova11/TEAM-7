import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';
import '../models/models.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.status, this.retryAfterSeconds, this.code});

  final String message;
  final int? status;
  final int? retryAfterSeconds;
  final String? code;

  bool get isConnection => status == null;

  @override
  String toString() => message;
}

/// Mobil tətbiq verilənləri YALNIZ REST API vasitəsilə alır (PostgreSQL-ə birbaşa qoşulmur).
class ApiClient {
  ApiClient(this.baseUrl, {http.Client? client}) : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 8);

  Uri _uri(String path, [Map<String, String>? query]) {
    final base = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    return Uri.parse('$base$path').replace(queryParameters: query);
  }

  Future<Map<String, dynamic>> _send(Future<http.Response> Function() call) async {
    final http.Response res;
    try {
      res = await call().timeout(_timeout);
    } on TimeoutException {
      throw ApiException('Server cavab vermir (vaxt bitdi). API ünvanı: $baseUrl');
    } catch (_) {
      throw ApiException('Serverə qoşulmaq mümkün olmadı. API ünvanı: $baseUrl');
    }
    Map<String, dynamic> body = <String, dynamic>{};
    try {
      final decoded = jsonDecode(utf8.decode(res.bodyBytes));
      if (decoded is Map<String, dynamic>) body = decoded;
    } catch (_) {
      // gövdə JSON deyil
    }
    if (res.statusCode >= 200 && res.statusCode < 300) return body;
    final detail = body['detail'];
    final msg = detail is String ? detail : 'Server xətası (${res.statusCode})';
    throw ApiException(
      msg,
      status: res.statusCode,
      retryAfterSeconds: (body['retry_after_seconds'] as num?)?.toInt() ??
          int.tryParse(res.headers['retry-after'] ?? ''),
      code: body['code'] as String?,
    );
  }

  Future<Map<String, dynamic>> _get(String path, [Map<String, String>? query]) =>
      _send(() => _client.get(_uri(path, query)));

  Future<Map<String, dynamic>> _post(String path, [Map<String, dynamic>? body]) => _send(() => _client.post(
        _uri(path),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body ?? <String, dynamic>{}),
      ));

  Future<List<RouteInfo>> routes() async {
    final j = await _get('/api/routes');
    return (j['routes'] as List).map((e) => RouteInfo.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<DirectionDetail> direction(int id) async =>
      DirectionDetail.fromJson(await _get('/api/directions/$id'));

  Future<Arrivals> arrivals(int directionId, String stopId) async => Arrivals.fromJson(
      await _get('/api/arrivals', {'direction_id': '$directionId', 'stop_id': stopId}));

  Future<List<StopSearchResult>> searchStops(String q) async {
    final j = await _get('/api/stops', {'q': q, 'limit': '15'});
    return (j['stops'] as List).map((e) => StopSearchResult.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// Vaxt göndərilmir: bildirişin vaxtını yalnız backend təyin edir.
  Future<void> report({required int busId, required String level, required String sessionId}) async {
    await _post('/api/reports', {'bus_id': busId, 'level': level, 'session_id': sessionId});
  }

  Future<OperatorOverview> overview() async => OperatorOverview.fromJson(await _get('/api/operator/overview'));

  Future<List<AlertInfo>> alerts({String status = 'ALL'}) async {
    final j = await _get('/api/operator/alerts', {'status': status, 'limit': '60'});
    return (j['alerts'] as List).map((e) => AlertInfo.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<DemoStatus> demoStatus() async => DemoStatus.fromJson(await _get('/api/demo/status'));

  Future<void> applyScenario(String name) async {
    await _post('/api/demo/scenarios/$name');
  }

  Future<void> resetDemo() async {
    await _post('/api/demo/reset');
  }
}

final ApiClient api = ApiClient(AppConfig.apiBaseUrl);
