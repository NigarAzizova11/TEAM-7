import 'package:latlong2/latlong.dart';

double? _d(Object? v) => v == null ? null : (v as num).toDouble();
int? _i(Object? v) => v == null ? null : (v as num).round();

class RouteInfo {
  RouteInfo({required this.id, required this.code, required this.name, required this.directions});

  final int id;
  final String code;
  final String name;
  final List<DirectionBrief> directions;

  factory RouteInfo.fromJson(Map<String, dynamic> j) => RouteInfo(
        id: j['id'] as int,
        code: j['code'] as String,
        name: j['name'] as String,
        directions: (j['directions'] as List)
            .map((e) => DirectionBrief.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class DirectionBrief {
  DirectionBrief({required this.id, required this.name, required this.buses, required this.stops});

  final int id;
  final String name;
  final int buses;
  final int stops;

  factory DirectionBrief.fromJson(Map<String, dynamic> j) => DirectionBrief(
        id: j['id'] as int,
        name: j['name'] as String,
        buses: j['buses'] as int,
        stops: j['stops'] as int,
      );
}

class StopPoint {
  StopPoint({
    required this.seq,
    required this.stopId,
    required this.name,
    required this.lat,
    required this.lon,
    required this.distanceM,
  });

  final int seq;
  final String stopId; // MƏTN: əvvəlindəki sıfırlar qorunur
  final String name;
  final double lat;
  final double lon;
  final int distanceM;

  LatLng get point => LatLng(lat, lon);

  factory StopPoint.fromJson(Map<String, dynamic> j) => StopPoint(
        seq: j['seq'] as int,
        stopId: j['stop_id'].toString(),
        name: j['name'] as String,
        lat: _d(j['lat'])!,
        lon: _d(j['lon'])!,
        distanceM: _i(j['distance_m']) ?? 0,
      );
}

class DirectionDetail {
  DirectionDetail({
    required this.id,
    required this.name,
    required this.routeName,
    required this.routeCode,
    required this.targetIntervalSeconds,
    required this.polyline,
    required this.stops,
  });

  final int id;
  final String name;
  final String routeName;
  final String routeCode;
  final int targetIntervalSeconds;
  final List<LatLng> polyline;
  final List<StopPoint> stops;

  factory DirectionDetail.fromJson(Map<String, dynamic> j) {
    final route = j['route'] as Map<String, dynamic>;
    return DirectionDetail(
      id: j['id'] as int,
      name: j['name'] as String,
      routeName: route['name'] as String,
      routeCode: route['code'] as String,
      targetIntervalSeconds: j['target_interval_seconds'] as int,
      polyline: (j['polyline'] as List).map((p) {
        final pair = p as List;
        return LatLng(_d(pair[0])!, _d(pair[1])!);
      }).toList(),
      stops: (j['stops'] as List).map((e) => StopPoint.fromJson(e as Map<String, dynamic>)).toList(),
    );
  }
}

class CrowdInfo {
  CrowdInfo({
    required this.level,
    required this.score,
    required this.reportsCount,
    required this.demoReportsCount,
    required this.latestAgeSeconds,
  });

  /// null => "Məlumat yoxdur" (heç vaxt "Aşağı" kimi göstərilmir)
  final String? level;
  final double? score;
  final int reportsCount;
  final int demoReportsCount;
  final int? latestAgeSeconds;

  factory CrowdInfo.fromJson(Map<String, dynamic> j) => CrowdInfo(
        level: j['level'] as String?,
        score: _d(j['score']),
        reportsCount: _i(j['reports_count']) ?? 0,
        demoReportsCount: _i(j['demo_reports_count']) ?? 0,
        latestAgeSeconds: _i(j['latest_report_age_seconds']),
      );
}

class BusView {
  BusView({
    required this.id,
    required this.code,
    required this.isSimulated,
    required this.lat,
    required this.lon,
    required this.speedKmh,
    required this.gpsAgeSeconds,
    required this.status,
    required this.etaSeconds,
    required this.distanceToStopM,
    required this.crowd,
  });

  final int id;
  final String code;
  final bool isSimulated;
  final double? lat;
  final double? lon;
  final double? speedKmh;
  final int? gpsAgeSeconds;
  final String status; // approaching | at_stop | passed | stopped | moving | offline
  final int? etaSeconds;
  final int? distanceToStopM;
  final CrowdInfo crowd;

  LatLng? get point => (lat == null || lon == null) ? null : LatLng(lat!, lon!);

  factory BusView.fromJson(Map<String, dynamic> j) => BusView(
        id: j['id'] as int,
        code: j['code'] as String,
        isSimulated: j['is_simulated'] as bool? ?? true,
        lat: _d(j['lat']),
        lon: _d(j['lon']),
        speedKmh: _d(j['speed_kmh']),
        gpsAgeSeconds: _i(j['gps_age_seconds']),
        status: j['status'] as String,
        etaSeconds: _i(j['eta_seconds']),
        distanceToStopM: _i(j['distance_to_stop_m']),
        crowd: CrowdInfo.fromJson(j['crowd'] as Map<String, dynamic>),
      );
}

class Alternative {
  Alternative({
    required this.firstBus,
    required this.busCode,
    required this.etaSeconds,
    required this.extraWaitSeconds,
    required this.firstLevel,
    required this.level,
    required this.dataAgeSeconds,
    required this.reportsCount,
  });

  final String firstBus;
  final String busCode;
  final int etaSeconds;
  final int extraWaitSeconds;
  final String? firstLevel;
  final String? level;
  final int? dataAgeSeconds;
  final int reportsCount;

  factory Alternative.fromJson(Map<String, dynamic> j) => Alternative(
        firstBus: j['first_bus'] as String,
        busCode: j['bus_code'] as String,
        etaSeconds: _i(j['eta_seconds']) ?? 0,
        extraWaitSeconds: _i(j['extra_wait_seconds']) ?? 0,
        firstLevel: j['first_level'] as String?,
        level: j['level'] as String?,
        dataAgeSeconds: _i(j['data_age_seconds']),
        reportsCount: _i(j['reports_count']) ?? 0,
      );
}

class Arrivals {
  Arrivals({
    required this.serverTime,
    required this.stopName,
    required this.buses,
    required this.alternative,
    required this.etaNote,
  });

  final DateTime serverTime;
  final String stopName;
  final List<BusView> buses;
  final Alternative? alternative;
  final String etaNote;

  factory Arrivals.fromJson(Map<String, dynamic> j) => Arrivals(
        serverTime: DateTime.parse(j['server_time'] as String),
        stopName: (j['stop'] as Map<String, dynamic>)['name'] as String,
        buses: (j['buses'] as List).map((e) => BusView.fromJson(e as Map<String, dynamic>)).toList(),
        alternative: j['alternative'] == null
            ? null
            : Alternative.fromJson(j['alternative'] as Map<String, dynamic>),
        etaNote: ((j['notes'] as Map<String, dynamic>)['eta'] ?? '') as String,
      );
}

class ServedBy {
  ServedBy({required this.directionId, required this.directionName, required this.routeName});

  final int directionId;
  final String directionName;
  final String routeName;

  factory ServedBy.fromJson(Map<String, dynamic> j) => ServedBy(
        directionId: j['direction_id'] as int,
        directionName: j['direction_name'] as String,
        routeName: j['route_name'] as String,
      );
}

class StopSearchResult {
  StopSearchResult({required this.stopId, required this.name, required this.servedBy});

  final String stopId;
  final String name;
  final List<ServedBy> servedBy;

  factory StopSearchResult.fromJson(Map<String, dynamic> j) => StopSearchResult(
        stopId: j['stop_id'].toString(),
        name: j['name'] as String,
        servedBy: (j['served_by'] as List)
            .map((e) => ServedBy.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

// ------------------------------------------------------------------ operator

class IntervalStats {
  IntervalStats({
    required this.medianS,
    required this.minS,
    required this.maxS,
    required this.samples,
    required this.targetS,
  });

  final int? medianS;
  final int? minS;
  final int? maxS;
  final int samples;
  final int targetS;

  factory IntervalStats.fromJson(Map<String, dynamic> j) => IntervalStats(
        medianS: _i(j['median_s']),
        minS: _i(j['min_s']),
        maxS: _i(j['max_s']),
        samples: _i(j['samples']) ?? 0,
        targetS: _i(j['target_s']) ?? 0,
      );
}

class LineCrowd {
  LineCrowd({
    required this.level,
    required this.score,
    required this.reasonNoResult,
    required this.busesWithData,
    required this.activeBuses,
    required this.latestReportAgeSeconds,
    required this.highForSeconds,
    required this.highThresholdSeconds,
  });

  final String? level;
  final double? score;
  final String? reasonNoResult;
  final int busesWithData;
  final int activeBuses;
  final int? latestReportAgeSeconds;
  final int highForSeconds;
  final int highThresholdSeconds;

  factory LineCrowd.fromJson(Map<String, dynamic> j) {
    final cov = j['coverage'] as Map<String, dynamic>;
    return LineCrowd(
      level: j['level'] as String?,
      score: _d(j['score']),
      reasonNoResult: j['reason_no_result'] as String?,
      busesWithData: _i(cov['buses_with_data']) ?? 0,
      activeBuses: _i(cov['active_buses']) ?? 0,
      latestReportAgeSeconds: _i(j['latest_report_age_seconds']),
      highForSeconds: _i(j['high_for_seconds']) ?? 0,
      highThresholdSeconds: _i(j['high_threshold_seconds']) ?? 600,
    );
  }
}

class OperatorDirection {
  OperatorDirection({
    required this.routeName,
    required this.routeCode,
    required this.directionId,
    required this.directionName,
    required this.targetIntervalSeconds,
    required this.intervals,
    required this.bunchingDetected,
    required this.diagnosis,
    required this.crowd,
    required this.activeBuses,
    required this.buses,
    required this.activeAlertIds,
  });

  final String routeName;
  final String routeCode;
  final int directionId;
  final String directionName;
  final int targetIntervalSeconds;
  final IntervalStats intervals;
  final bool bunchingDetected;
  final String diagnosis;
  final LineCrowd crowd;
  final int activeBuses;
  final List<BusView> buses;
  final List<int> activeAlertIds;

  factory OperatorDirection.fromJson(Map<String, dynamic> j) {
    final route = j['route'] as Map<String, dynamic>;
    final dir = j['direction'] as Map<String, dynamic>;
    return OperatorDirection(
      routeName: route['name'] as String,
      routeCode: route['code'] as String,
      directionId: dir['id'] as int,
      directionName: dir['name'] as String,
      targetIntervalSeconds: _i(j['target_interval_seconds']) ?? 0,
      intervals: IntervalStats.fromJson(j['intervals'] as Map<String, dynamic>),
      bunchingDetected: j['bunching_detected'] as bool? ?? false,
      diagnosis: j['diagnosis'] as String? ?? 'unclear',
      crowd: LineCrowd.fromJson(j['crowd'] as Map<String, dynamic>),
      activeBuses: _i(j['active_buses']) ?? 0,
      buses: (j['buses'] as List).map((e) => BusView.fromJson(e as Map<String, dynamic>)).toList(),
      activeAlertIds: (j['active_alert_ids'] as List).map((e) => (e as num).toInt()).toList(),
    );
  }
}

class OperatorOverview {
  OperatorOverview({
    required this.serverTime,
    required this.directions,
    required this.activeAlertsCount,
    required this.highCrowdMinutes,
    required this.rulesNote,
  });

  final DateTime serverTime;
  final List<OperatorDirection> directions;
  final int activeAlertsCount;
  final int highCrowdMinutes;
  final String rulesNote;

  factory OperatorOverview.fromJson(Map<String, dynamic> j) {
    final rules = j['rules'] as Map<String, dynamic>;
    return OperatorOverview(
      serverTime: DateTime.parse(j['server_time'] as String),
      directions: (j['directions'] as List)
          .map((e) => OperatorDirection.fromJson(e as Map<String, dynamic>))
          .toList(),
      activeAlertsCount: _i(j['active_alerts_count']) ?? 0,
      highCrowdMinutes: _i(rules['high_crowd_minutes']) ?? 10,
      rulesNote: (rules['note'] ?? '') as String,
    );
  }
}

class AlertInfo {
  AlertInfo({
    required this.id,
    required this.kind,
    required this.status,
    required this.title,
    required this.event,
    required this.possibleCause,
    required this.evidence,
    required this.recommendation,
    required this.createdAt,
    required this.resolvedAt,
    required this.isDemo,
    required this.routeName,
    required this.directionName,
  });

  final int id;
  final String kind;
  final String status; // ACTIVE | RESOLVED
  final String title;
  final String event;
  final String possibleCause;
  final Map<String, dynamic> evidence;
  final String recommendation;
  final DateTime createdAt;
  final DateTime? resolvedAt;
  final bool isDemo;
  final String routeName;
  final String directionName;

  bool get active => status == 'ACTIVE';

  factory AlertInfo.fromJson(Map<String, dynamic> j) => AlertInfo(
        id: j['id'] as int,
        kind: j['kind'] as String,
        status: j['status'] as String,
        title: j['title'] as String,
        event: j['event'] as String,
        possibleCause: j['possible_cause'] as String,
        evidence: Map<String, dynamic>.from(j['evidence'] as Map),
        recommendation: j['recommendation'] as String,
        createdAt: DateTime.parse(j['created_at'] as String),
        resolvedAt: j['resolved_at'] == null ? null : DateTime.parse(j['resolved_at'] as String),
        isDemo: j['is_demo'] as bool? ?? true,
        routeName: (j['route'] as Map<String, dynamic>)['name'] as String,
        directionName: (j['direction'] as Map<String, dynamic>)['name'] as String,
      );
}

class ScenarioInfo {
  ScenarioInfo({required this.name, required this.label, required this.description});

  final String name;
  final String label;
  final String description;

  factory ScenarioInfo.fromJson(Map<String, dynamic> j) => ScenarioInfo(
        name: j['name'] as String,
        label: j['label'] as String,
        description: j['description'] as String,
      );
}

class DemoStatus {
  DemoStatus({
    required this.stopsLoaded,
    required this.structureReady,
    required this.activeScenario,
    required this.scenarios,
  });

  final int stopsLoaded;
  final bool structureReady;
  final String? activeScenario;
  final List<ScenarioInfo> scenarios;

  factory DemoStatus.fromJson(Map<String, dynamic> j) => DemoStatus(
        stopsLoaded: _i(j['stops_loaded']) ?? 0,
        structureReady: j['structure_ready'] as bool? ?? false,
        activeScenario: j['active_scenario'] as String?,
        scenarios: (j['scenarios'] as List)
            .map((e) => ScenarioInfo.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
