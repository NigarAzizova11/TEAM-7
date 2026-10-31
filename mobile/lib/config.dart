/// API baza ünvanı yalnız build zamanı `--dart-define` ilə verilir.
///
///   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
///
/// Bu tətbiqə heç bir məxfi məlumat (DB parolu, açar) daxil edilmir: yalnız REST API ünvanı.
class AppConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000', // Android emulatorunda host maşın
  );

  /// Dövri yenilənmə müddəti (saniyə). Ekran aktiv olmayanda polling dayanır.
  static const int pollSeconds = 5;

  static const String osmTileUrl = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  static const String tileUserAgent = 'az.bakuflow.bakuflow_mobile';
}
