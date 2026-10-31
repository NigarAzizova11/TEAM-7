"""Tətbiq konfiqurasiyası. Bütün hədlər mühit dəyişənləri ilə dəyişdirilə bilər.

Qeyd: buradakı hədlər DEMO qaydalarıdır, təsdiqlənmiş nəqliyyat standartları deyil.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Məcburi (default yoxdur: konfiqurasiya olmadan başlamasın) ---
    database_url: str
    session_hash_secret: str

    # --- Ümumi ---
    cors_origins: str = ""  # vergüllə ayrılmış; mobil tətbiq üçün lazım deyil
    demo_endpoints_enabled: bool = True
    sim_autostart: bool = True
    sim_tick_seconds: int = 5
    sim_history_minutes: int = 20  # demo seed-in geriyə yaratdığı GPS tarixçəsi
    sim_history_step_seconds: int = 10

    # --- Sıxlıq ---
    crowd_window_minutes: int = 5  # bildirişin etibarlılıq müddəti
    crowd_low_max: float = 1.5  # orta bal <= bu => AŞAĞI
    crowd_high_min: float = 2.5  # orta bal >= bu => YÜKSƏK
    bus_min_reports: int = 1  # avtobusun nəticəsi üçün minimum bildiriş
    line_min_coverage_ratio: float = 0.5  # məlumatı olan / aktiv avtobus
    report_cooldown_seconds: int = 60  # eyni sessiya + eyni avtobus
    gps_stale_seconds: int = 30  # bundan köhnə GPS => avtobus aktiv sayılmır

    # --- 10 dəqiqəlik qayda ---
    high_crowd_minutes: int = 10
    persistence_step_seconds: int = 60  # davamlılığın yoxlanma addımı
    persistence_cap_minutes: int = 30  # göstərilən davamlılığın yuxarı həddi

    # --- İnterval / qruplaşma ---
    interval_lookback_minutes: int = 20
    bunch_small_ratio: float = 0.4  # kiçik interval < hədəf * bu
    bunch_large_ratio: float = 1.6  # arxadakı boşluq > hədəf * bu
    bunch_min_stops: int = 2  # neçə dayanacaqda müşahidə olunmalıdır
    interval_ok_low: float = 0.6  # median interval hədəfin bu qədərindən az olmasın
    interval_ok_high: float = 1.5  # ... və bu qədərindən çox olmasın

    # --- Mümkün yol ləngiməsi ---
    slow_lookback_minutes: int = 10
    slow_speed_ratio: float = 0.5  # seqmentdə orta sürət < baza * bu
    slow_min_buses: int = 2
    slow_min_samples: int = 3

    # --- Qeyri-adi dayanma ---
    unusual_stop_minutes: int = 3
    unusual_stop_max_speed_mps: float = 0.5
    unusual_stop_max_drift_m: float = 25.0
    unusual_stop_min_stop_distance_m: float = 60.0
    others_moving_mps: float = 1.5

    # --- Tıxac (sərnişin bildirişləri əsasında; real trafik sensoru YOXDUR) ---
    traffic_window_minutes: int = 15  # bildirişin etibarlılıq müddəti
    traffic_cluster_gap_m: float = 400.0  # bu məsafədən yaxın bildirişlər bir tıxac sayılır
    traffic_min_reports: int = 2  # təsdiq üçün minimum fərqli sərnişin
    traffic_alert_min_reports: int = 1  # operatora düşmək üçün minimum fərqli sərnişin (ağır bildiriş). <2 olduqda xəbərdarlıq 'təsdiqlənməyib' kimi işarələnir
    traffic_snap_max_m: float = 150.0  # bildiriş nöqtəsi xəttdən bu qədər uzaqda ola bilməz
    traffic_cooldown_seconds: int = 60  # eyni sessiya + eyni istiqamət
    traffic_medium_min: float = 1.7  # orta bal >= bu => ORTA
    traffic_heavy_min: float = 2.4  # orta bal >= bu => AĞIR

    # --- ETA ---
    eta_speed_window_seconds: int = 60
    eta_stopped_speed_mps: float = 0.3

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
