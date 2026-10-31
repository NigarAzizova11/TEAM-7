import 'package:flutter/material.dart';

import '../config.dart';
import '../widgets/common.dart';
import 'operator_screen.dart';
import 'passenger_screen.dart';

/// DEMO girişi. Bu seçim real autentifikasiya və ya icazə sistemi DEYİL.
class RoleSelectScreen extends StatelessWidget {
  const RoleSelectScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                const SizedBox(height: 12),
                Text('BakuFlow', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800)),
                const Text('Smart Transit & Crowdsourcing Engine'),
                const SizedBox(height: 16),
                const DemoBanner(
                  'DEMO: dayanacaqlar real məlumatdır; marşrutlar ("Demo A/B"), avtobus GPS-i və demo bildirişləri '
                  'SİMULYASİYADIR. Aşağıdakı seçim real giriş və ya icazə sistemi deyil.',
                ),
                const SizedBox(height: 16),
                _RoleCard(
                  icon: Icons.person_pin_circle,
                  title: 'Sərnişin',
                  subtitle: 'Dayanacaq seç, avtobusun yerini və ETA-nı gör, sıxlığı bildir',
                  onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const PassengerScreen())),
                ),
                const SizedBox(height: 12),
                _RoleCard(
                  icon: Icons.monitor_heart,
                  title: 'Operator',
                  subtitle: 'Xətlər üzrə sıxlıq, intervallar, xəbərdarlıqlar, demo idarəetməsi',
                  onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const OperatorScreen())),
                ),
                const SizedBox(height: 20),
                Text(
                  'Prototip: operator ekranı autentifikasiyasızdır.\nAPI: ${AppConfig.apiBaseUrl}',
                  style: const TextStyle(fontSize: 12, color: Color(0xFF616161)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _RoleCard extends StatelessWidget {
  const _RoleCard({required this.icon, required this.title, required this.subtitle, required this.onTap});

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(
            children: [
              Icon(icon, size: 40, color: Theme.of(context).colorScheme.primary),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 4),
                    Text(subtitle),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right),
            ],
          ),
        ),
      ),
    );
  }
}
