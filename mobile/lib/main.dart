import 'package:flutter/material.dart';

import 'screens/role_select_screen.dart';
import 'util/polling.dart';

void main() => runApp(const BakuFlowApp());

class BakuFlowApp extends StatelessWidget {
  const BakuFlowApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BakuFlow',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF0B5FA5),
        useMaterial3: true,
      ),
      navigatorObservers: [routeObserver],
      home: const RoleSelectScreen(),
    );
  }
}
