import 'package:flutter/material.dart';

String fmtDuration(num seconds) {
  final s = seconds.round();
  if (s < 60) return '$s san';
  final m = s ~/ 60;
  final r = s % 60;
  return r == 0 ? '$m dəq' : '$m dəq $r san';
}

/// "12 san əvvəl", "3 dəq əvvəl"; null => "—"
String fmtAge(int? seconds) {
  if (seconds == null) return '—';
  if (seconds < 5) return 'indicə';
  if (seconds < 60) return '$seconds san əvvəl';
  return '${seconds ~/ 60} dəq əvvəl';
}

String fmtEta(int? seconds) {
  if (seconds == null) return '—';
  if (seconds < 20) return 'indi';
  if (seconds < 90) return '~1 dəq';
  return '~${(seconds / 60).round()} dəq';
}

String two(int v) => v.toString().padLeft(2, '0');

String fmtClock(DateTime dt) {
  final l = dt.toLocal();
  return '${two(l.hour)}:${two(l.minute)}:${two(l.second)}';
}

// ------------------------------------------------------------------ sıxlıq

/// null => "Məlumat yoxdur": heç vaxt "Aşağı" kimi göstərilmir.
String crowdLabel(String? level) {
  switch (level) {
    case 'LOW':
      return 'Aşağı';
    case 'MEDIUM':
      return 'Orta';
    case 'HIGH':
      return 'Yüksək';
    default:
      return 'Məlumat yoxdur';
  }
}

Color crowdColor(String? level) {
  switch (level) {
    case 'LOW':
      return const Color(0xFF2E7D32);
    case 'MEDIUM':
      return const Color(0xFFB26A00);
    case 'HIGH':
      return const Color(0xFFC62828);
    default:
      return const Color(0xFF616161);
  }
}

Color crowdBackground(String? level) {
  switch (level) {
    case 'LOW':
      return const Color(0xFFE8F5E9);
    case 'MEDIUM':
      return const Color(0xFFFFF3E0);
    case 'HIGH':
      return const Color(0xFFFFEBEE);
    default:
      return const Color(0xFFEEEEEE);
  }
}

/// Rəngə əlavə olaraq işarə: rəng korluğu olan istifadəçilər də ayırd edə bilsin.
IconData crowdIcon(String? level) {
  switch (level) {
    case 'LOW':
      return Icons.sentiment_satisfied_alt;
    case 'MEDIUM':
      return Icons.sentiment_neutral;
    case 'HIGH':
      return Icons.sentiment_very_dissatisfied;
    default:
      return Icons.help_outline;
  }
}

String busStatusLabel(String status) {
  switch (status) {
    case 'approaching':
      return 'Yaxınlaşır';
    case 'at_stop':
      return 'Dayanacaqdadır';
    case 'passed':
      return 'Dayanacağı keçib';
    case 'stopped':
      return 'Dayanıb';
    case 'moving':
      return 'Hərəkətdədir';
    default:
      return 'Siqnal yoxdur';
  }
}

String noResultReason(String? reason) {
  switch (reason) {
    case 'no_active_buses':
      return 'Aktiv avtobus yoxdur';
    case 'low_coverage':
      return 'Məlumat əhatəsi kifayət deyil';
    case 'no_data':
      return 'Aktual bildiriş yoxdur';
    default:
      return 'Məlumat yoxdur';
  }
}

String diagnosisLabel(String d) {
  switch (d) {
    case 'capacity':
      return 'Tutum çatışmazlığı ehtimalı: intervallar normal, sıxlıq yüksək';
    case 'interval':
      return 'Mümkün interval pozuntusu (qruplaşma)';
    default:
      return 'Səbəb aydın deyil';
  }
}

String alertKindLabel(String kind) {
  switch (kind) {
    case 'HIGH_CROWD_10MIN':
      return 'Davamlı yüksək sıxlıq';
    case 'BUNCHING':
      return 'Avtobusların qruplaşması';
    case 'POSSIBLE_SLOWDOWN':
      return 'Mümkün yol ləngiməsi';
    case 'UNUSUAL_STOP':
      return 'Qeyri-adi dayanma';
    default:
      return kind;
  }
}

const Map<String, String> evidenceLabels = {
  'line_level': 'Xətt üzrə sıxlıq',
  'line_score': 'Orta bal (1-3)',
  'high_for_seconds': 'Fasiləsiz yüksək müddəti (san)',
  'threshold_seconds': 'Hədd (san)',
  'coverage': 'Əhatə (məlumatlı / aktiv avtobus)',
  'latest_report_age_seconds': 'Son bildirişin yaşı (san)',
  'report_window_minutes': 'Bildiriş pəncərəsi (dəq)',
  'reports_in_window': 'Pəncərədəki bildirişlər',
  'high_buses': 'Yüksək sıxlıqlı avtobuslar',
  'observed_interval_median_s': 'Müşahidə olunan median interval (san)',
  'target_interval_s': 'Hədəf interval (san)',
  'bunching_detected': 'Qruplaşma aşkarlanıb',
  'diagnosis': 'Diaqnoz',
  'pair': 'Avtobus cütü (öndəki, arxadakı)',
  'gap_small_s': 'Cüt arası interval (san)',
  'gap_large_s': 'Arxadakı boşluq (san)',
  'stops_flagged': 'Müşahidə olunan dayanacaq sayı',
  'example_stops': 'Nümunə dayanacaqlar',
  'observed_intervals': 'Müşahidə olunan intervallar',
  'segment_index': 'Seqment indeksi',
  'from_stop': 'Seqmentin başlanğıcı',
  'to_stop': 'Seqmentin sonu',
  'buses': 'Avtobuslar',
  'baseline_kmh': 'Baza sürət (km/s)',
  'threshold_ratio': 'Yavaşlama hədd nisbəti',
  'lookback_minutes': 'Baxış pəncərəsi (dəq)',
  'bus': 'Avtobus',
  'stopped_for_seconds': 'Hərəkətsizlik müddəti (san)',
  'distance_to_nearest_stop_m': 'Ən yaxın dayanacağa məsafə (m)',
  'other_buses_moving': 'Hərəkət edən digər avtobuslar',
  'avg_speed_kmh': 'orta sürət (km/s)',
  'samples': 'ölçmə sayı',
  'median_s': 'median (san)',
  'min_s': 'min (san)',
  'max_s': 'maks (san)',
  'target_s': 'hədəf (san)',
  'buses_with_data': 'məlumatlı avtobus',
  'active_buses': 'aktiv avtobus',
  'user': 'istifadəçi',
  'demo_seed': 'demo',
};

String evidenceValue(Object? v) {
  if (v == null) return '—';
  if (v is bool) return v ? 'bəli' : 'xeyr';
  if (v is List) return v.map(evidenceValue).join(', ');
  if (v is Map) return v.entries.map((e) => '${evidenceLabelOrKey(e.key.toString())}: ${evidenceValue(e.value)}').join('; ');
  if (v is double) return v.toStringAsFixed(v == v.roundToDouble() ? 0 : 2);
  return v.toString();
}

String evidenceLabelOrKey(String k) => evidenceLabels[k] ?? k;
