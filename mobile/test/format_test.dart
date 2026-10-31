import 'package:flutter_test/flutter_test.dart';

import 'package:bakuflow_mobile/models/models.dart';
import 'package:bakuflow_mobile/util/format.dart';

void main() {
  test('məlumat yoxdursa "Aşağı" yox, "Məlumat yoxdur" göstərilir', () {
    expect(crowdLabel(null), 'Məlumat yoxdur');
    expect(crowdLabel('LOW'), 'Aşağı');
    expect(crowdLabel('MEDIUM'), 'Orta');
    expect(crowdLabel('HIGH'), 'Yüksək');
  });

  test('müddət və yaş formatı', () {
    expect(fmtDuration(45), '45 san');
    expect(fmtDuration(600), '10 dəq');
    expect(fmtDuration(125), '2 dəq 5 san');
    expect(fmtAge(null), '—');
    expect(fmtAge(30), '30 san əvvəl');
    expect(fmtAge(180), '3 dəq əvvəl');
  });

  test('stop_id mətn kimi qalır (sıfırlar itmir)', () {
    final s = StopPoint.fromJson({'seq': 0, 'stop_id': '00042', 'name': 'x', 'lat': 40, 'lon': 49, 'distance_m': 0});
    expect(s.stopId, '00042');
    expect(s.lat, 40.0);
  });

  test('crowd.level null qalır', () {
    final c = CrowdInfo.fromJson({'level': null, 'score': null, 'reports_count': 0, 'demo_reports_count': 0, 'latest_report_age_seconds': null});
    expect(c.level, isNull);
  });
}
