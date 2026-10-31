import 'package:flutter/material.dart';

import '../util/format.dart';

/// Sıxlıq: rəng + işarə + MƏTN (yalnız rəngə güvənmir).
class CrowdChip extends StatelessWidget {
  const CrowdChip({super.key, required this.level, this.compact = false});

  final String? level; // null => "Məlumat yoxdur"
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final color = crowdColor(level);
    return Semantics(
      label: 'Sıxlıq: ${crowdLabel(level)}',
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: compact ? 8 : 10, vertical: compact ? 3 : 5),
        decoration: BoxDecoration(
          color: crowdBackground(level),
          border: Border.all(color: color, width: 1.2),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(crowdIcon(level), size: compact ? 14 : 18, color: color),
            const SizedBox(width: 5),
            Text(
              crowdLabel(level),
              style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: compact ? 12 : 14),
            ),
          ],
        ),
      ),
    );
  }
}

/// Real və simulyasiya məlumatını aydın ayıran etiket.
class Tag extends StatelessWidget {
  const Tag(this.text, {super.key, this.color = const Color(0xFF6A1B9A)});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        border: Border.all(color: color),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(text, style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w700)),
    );
  }
}

class DemoBanner extends StatelessWidget {
  const DemoBanner(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFFF3E5F5),
        border: Border.all(color: const Color(0xFF6A1B9A)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.science_outlined, color: Color(0xFF6A1B9A), size: 20),
          const SizedBox(width: 8),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 12.5, color: Color(0xFF4A148C)))),
        ],
      ),
    );
  }
}

class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.message = 'Yüklənir...'});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 12),
            Text(message),
          ],
        ),
      ),
    );
  }
}

class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 48, color: Color(0xFFC62828)),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            if (onRetry != null) ...[
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('Yenidən cəhd et'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class EmptyView extends StatelessWidget {
  const EmptyView({super.key, required this.message, this.icon = Icons.inbox_outlined});

  final String message;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48, color: const Color(0xFF757575)),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

/// Yenilənmə uğursuz olanda: köhnə məlumat göstərilir, lakin bu aydın bildirilir.
class StaleBanner extends StatelessWidget {
  const StaleBanner({super.key, required this.message, this.lastOk, this.onRetry});

  final String message;
  final DateTime? lastOk;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFFFFEBEE),
        border: Border.all(color: const Color(0xFFC62828)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          const Icon(Icons.wifi_off, color: Color(0xFFC62828), size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              lastOk == null
                  ? message
                  : '$message\nSon uğurlu yenilənmə: ${fmtClock(lastOk!)} (göstərilən məlumat köhnə ola bilər)',
              style: const TextStyle(fontSize: 12.5),
            ),
          ),
          if (onRetry != null) IconButton(onPressed: onRetry, icon: const Icon(Icons.refresh)),
        ],
      ),
    );
  }
}
