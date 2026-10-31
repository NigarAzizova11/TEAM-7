# BakuFlow — Smart Transit & Crowdsourcing Engine (hackathon prototipi)

Bakı avtobuslarında pik saat sıxlığı üçün sərnişin + operator prototipi.
Fərq: yalnız sıxlığı göstərmək yox, **GPS + intervallar + sərnişin bildirişlərini** birləşdirib operatora
*mümkün səbəb, ölçülmüş sübut və tövsiyə* verir. Əsas sual: **"Əlavə avtobus lazımdır, yoxsa mövcud avtobusların intervallarını düzəltmək?"**

> **Əvvəlcə dürüst qeyd.** Bu bir prototipdir. **Real:** dayanacaqlar (`dayanacaqlar.csv` və AYNA), marşrut xətləri və dayanacaq
> sıralaması (map.ayna.gov.az-ın öz API cavabından, 198 marşrut). **Simulyasiya:** avtobusların mövqeyi/GPS-i (12 marşrutda),
> demo sıxlıq bildirişləri. **Sərnişin bildirişlərinə əsaslanan:** yol tıxacı (real trafik sensoru yoxdur).
> Qaydalar (hədlər) **demo qaydalarıdır**, təsdiqlənmiş nəqliyyat standartı deyil. Sistem qəza və ya sürücü günahı
> iddia etmir ("mümkün yol ləngiməsi", "qeyri-adi dayanma" kimi ehtimal ifadələri işlədir), sürücüyə avtomatik əmr göndərmir.
> Flutter kodu (`mobile/`) kompilyasiya edilməyib; işləyən interfeys veb səhifədir (`/web/`, telefonda PWA kimi də açılır).

**Komanda:** Team 7 · Hackathon: Digital Challenge

**Canlı demo:** https://bakuflow.onrender.com/web/
> Render-in pulsuz planı olduğu üçün sayt 15 dəqiqə istifadə olunmadıqda yatır; ilk açılış ~1 dəqiqə çəkə bilər.

## Strukturu

```
backend/            FastAPI + SQLAlchemy + Alembic (Python)
  app/
    routers/        REST endpointləri (passenger, operator, demo)
    services/       csv_import, simulator, crowd, analysis, demo, views, reports, ticker
    models.py       PostgreSQL modelləri (UTC, timezone-aware)
  alembic/          miqrasiyalar
  tests/            pytest (PostgreSQL üzərində)
  data/             dayanacaqlar.csv bura qoyulur (git-ə düşmür)
mobile/             Flutter (Android + iOS), sərnişin və operator ayrı ekranlar
docker-compose.yml  backend + PostgreSQL
.env.example
```

## Arxitektura

```
 ┌────────────────────┐   REST (JSON, hər 5 san polling;     ┌───────────────────────────────┐
 │ Flutter tətbiqi    │   ekran aktiv olmayanda dayanır)      │ FastAPI backend               │
 │  · Sərnişin ekranı │ ────────────────────────────────────▶ │  routers → services           │
 │  · Operator ekranı │ ◀──────────────────────────────────── │   views / reports / demo      │
 └────────────────────┘   (PostgreSQL-ə birbaşa qoşulmur)      │                               │
                                                               │  ticker (hər 5 san, backend   │
                                                               │  daxilində):                  │
                                                               │   1. simulator → GPS yazır    │
                                                               │   2. demo bildirişlərini      │
                                                               │      təzələyir (açıq işarəli) │
                                                               │   3. analysis.evaluate():     │
                                                               │      sıxlıq, 10 dəq qaydası,  │
                                                               │      interval, ləngimə,       │
                                                               │      dayanma → alerts         │
                                                               └──────────────┬────────────────┘
                                                                              │ SQLAlchemy
                                                               ┌──────────────▼────────────────┐
                                                               │ PostgreSQL                    │
                                                               │ stops (REAL), routes,         │
                                                               │ directions, direction_stops,  │
                                                               │ buses, gps_positions,         │
                                                               │ crowd_reports, alerts,        │
                                                               │ demo_state                    │
                                                               └───────────────────────────────┘
```

Əsas qərarlar:
- **Vahid saat** (`app/clock.py`): bütün vaxtlar buradan alınır (UTC, timezone-aware). Testlər saatı dondurub irəli aparır; **10 dəqiqəlik qayda heç yerdə qısaldılmır**.
- **Simulyator** yalnız lat/lon/sürət yazır; analiz bu nöqtələri sxematik xəttə proyeksiya edir (real GPS ilə eyni yol).
- **Xəbərdarlığın təkrarı** iki qatda əngəllənir: kodda (`dedup_key`) və DB-də (aktiv xəbərdarlıq üçün qismən unikal indeks).

## Məlumat: nə real, nə simulyasiyadır

| Məlumat | Mənbə | UI-da |
|---|---|---|
| Dayanacaqlar | **REAL**: `dayanacaqlar.csv` + CSV-də olmayanlar AYNA-nın öz dayanacaq adı/koordinatı ilə (`stop_type=AYNA`) | "real dayanacaq" |
| 198 marşrut, istiqamətlər, dayanacaq ardıcıllığı, xətt geometriyası | **REAL**, map.ayna.gov.az-ın öz API cavabından (`backend/data/ayna_routes.json`, xətt ~8 m dəqiqliyə sadələşdirilib). AYNA-da olmayan/xəta verən marşrutlar (məs. 144, 531) yoxdur | "AYNA marşrutu" |
| Avtobusların sayı, hədəf interval (`--headway`) | **VARSAYIM** (AYNA bunu vermir) | "SİMULYASİYA" |
| Avtobuslar, GPS, sürət (yalnız 12 marşrutda) | **SİMULYASİYA** (backend daxilində); xəritədə marşrut nömrəsi ilə göstərilir | "(simulyasiya)" |
| ETA | Real xətt boyunca qalan məsafə / simulyasiya sürəti. **Real gəliş vədi deyil** | ETA qeydi |
| Sıxlıq bildirişləri | İstifadəçilərdən (`source=user`) və ssenari tərəfindən (`source=demo_seed`, açıq işarəli) | "demo" sayı |
| **Yol tıxacı** | **Sərnişin bildirişləri** (real trafik sensoru/Waze/Google yoxdur) | "təsdiqlənməyib" / səviyyə |
| Alternativ yol | OSRM ictimai demo serveri (canlı tıxacı bilmir, yalnız tıxac nöqtəsindən yan keçən yol) | mavi qırıq xətt |
| Xəbərdarlıqlar | Real analiz kodu nəticəsi; demo məlumatdan yarananlar "DEMO" işarəlidir | "DEMO" etiketi |

AYNA datası `tools/fetch_ayna_routes_browser.js` ilə (və ya `fetch_ayna_routes.py`) bir dəfə çıxarılır. Backend işləyərkən AYNA API-sinə sorğu **göndərilmir**.
Canlı GPS yoxdur. Sərnişin gediş datasetı (`bakubus_passenger-2026.csv`) hələ **inteqrasiya olunmayıb**.

## Sıxlıq hesablaması və qaydalar (hamısı `backend/app/config.py`-da konfiqurasiya olunur)

- Aşağı = 1, Orta = 2, Yüksək = 3. Bildirişin etibarlılığı **5 dəqiqə**.
- Avtobus balı = son 5 dəq bildirişlərin ortası. Bildiriş yoxdursa nəticə **"Məlumat yoxdur"** (heç vaxt "Aşağı" yox).
  Hədlər: bal ≤ 1.5 Aşağı, ≥ 2.5 Yüksək, arası Orta.
- Xətt balı yalnız **aktual məlumatı olan aktiv avtobuslardan** hesablanır; əhatə (məlumatlı/aktiv) ≥ 50% olmalıdır və göstərilir.
- **10 dəqiqəlik qayda:** `now, now−1dəq, …, now−10dəq` nöqtələrinin **hər birində** (həmin anda etibarlı bildirişlərlə) xətt "Yüksək" olarsa
  → **"Əlavə avtobus ehtiyatı ayrılmalıdır"** xəbərdarlığı. Məlumat köhnələndə, əhatə azalanda və ya sıxlıq düşəndə davamlılıq sıfırlanır.
  Bir köhnə bildiriş 10 dəqiqə sonra təkbaşına xəbərdarlıq yarada bilməz. Şərt aradan qalxanda xəbərdarlıq **həll olunur**; yenidən yaranması üçün 10 dəqiqə yenidən lazımdır.
- **Diaqnoz** (əsas suala cavab): intervallar normal + ≥2 avtobus yüksək → *tutum çatışmazlığı ehtimalı* (ehtiyat tövsiyəsi);
  qruplaşma aşkarlanıbsa → *əvvəlcə intervalın bərpası*.
- Qruplaşma: eyni istiqamətdə ardıcıl avtobusların eyni dayanacaqdan keçmə vaxtlarından interval ölçülür (əks istiqamətlər qarışmır);
  kiçik interval + arxada böyük boşluq ≥ 2 dayanacaqda müşahidə olunarsa xəbərdarlıq.
- Mümkün yol ləngiməsi: eyni sxematik hissədə ≥ 2 avtobus birlikdə yavaşlayarsa.
- Qeyri-adi dayanma: avtobus dayanacaqdan ≥ 60 m kənarda ≥ 3 dəq hərəkətsizdir, digərləri hərəkət edir.
- Hər xəbərdarlıqda: hadisə, mümkün səbəb, ölçülmüş sübut, operatora tövsiyə, yaranma vaxtı, aktiv/həll olunmuş.

## Lokal başlatma

### 1) Backend + PostgreSQL (Docker Compose)

```bash
cp .env.example .env            # və POSTGRES_PASSWORD, SESSION_HASH_SECRET dəyərlərini dəyişin
# Real faylı bura qoyun:
cp /yol/dayanacaqlar.csv backend/data/dayanacaqlar.csv

docker compose up -d --build    # db + backend (miqrasiyalar konteyner başlayanda avtomatik tətbiq olunur)
docker compose logs -f backend  # "Uvicorn running" gözləyin
```

### 2) Miqrasiya, CSV importu, demo seed

```bash
# Miqrasiya (konteynerdə artıq işləyib; əl ilə təkrar):
docker compose exec backend alembic upgrade head

# Dayanacaqları yüklə (təkrar işlətmək təhlükəsizdir: eyni stop_id çoxalmır, dəyişənlər yenilənir)
docker compose exec backend python -m app.cli import-stops --file data/dayanacaqlar.csv

# REAL AYNA marşrut strukturunu yüklə (dayanacaq ardıcıllığı + xətt geometriyası; backend/data/ayna_routes.json)
docker compose exec backend python -m app.cli import-routes --file data/ayna_routes.json --headway 5

# Avtobus hərəkətini (SİMULYASİYA) qur və "normal" ssenarini tətbiq et
docker compose exec backend python -m app.cli seed-demo --scenario normal

docker compose exec backend python -m app.cli status
```

CSV qaydaları: başlıq `ID,AD,ID,LONGITUDE,LATITUDE,Tip`; sütunlar **mövqeyə görə** oxunur (1-ci ID = `row_id`, 2-ci ID = `stop_id`);
`stop_id` mətn kimi saxlanır (sıfırlar qorunur); koordinatlar onluq dərəcədir (bölünmür); `Tip` boş ola bilər;
eyni adlı müxtəlif dayanacaqlar birləşdirilmir. Etibarsız sətirlər səbəbi ilə hesabatda göstərilir.

API sənədi: http://localhost:8000/docs · sağlamlıq: http://localhost:8000/health

**Docker olmadan** (lokal PostgreSQL ilə):

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://USER:PAROL@127.0.0.1:5432/bakuflow
export SESSION_HASH_SECRET=uzun-tesadufi-metn
alembic upgrade head
python -m app.cli import-stops --file data/dayanacaqlar.csv
python -m app.cli seed-demo --scenario normal
uvicorn app.main:app --host 0.0.0.0 --port 8000     # tək worker (simulyator dövrü bir dəfə işləməlidir)
```

### 2.0) Bütün AYNA marşrutlarını yükləmək (bir dəfə, öz kompüterinizdə)

`backend/data/ayna_routes.json` repoda hazırdır (199 marşrut, 3456 AYNA dayanacağının adı/koordinatı ilə). Yenidən götürmək üçün host kompüterdə (Docker xaricində, Python 3 kifayətdir):

```powershell
python backend\tools\fetch_ayna_routes.py --out backend\data\ayna_routes.json     # ~1-2 dəq
docker compose exec backend python -m app.cli import-routes --file data/ayna_routes.json
docker compose exec backend python -m app.cli seed-demo --scenario normal
```

Python SSL sertifikat xətası verərsə (`CERTIFICATE_VERIFY_FAILED`, şəbəkə sertifikat müdaxiləsi): TLS yoxlamasını söndürməyin; `pip install certifi` edin
və ya **brauzer variantını** işlədin: `https://map.ayna.gov.az/` açın → `F12` → Console → `backend/tools/fetch_ayna_routes_browser.js` faylının
məzmununu yapışdırın → `ayna_routes.json` endirilir (Downloads), onu `backend\data\` qovluğuna atın. (Sınaqda 199 marşrut ~6 saniyəyə gəldi.)

Bütün marşrutların **real xətti və dayanacaq sırası** bazaya yazılır. Avtobus simulyasiyası yalnız `--simulate` ilə seçilən marşrutlar üçün qurulur
(default: sərnişin datasetində ən yüklü 12 marşrut); qalanları "yalnız xətt" kimi göstərilir. Hamısını simulyasiya etmək (`--simulate all`) minlərlə avtobus yaradıb analizi ləngidər.
Skript AYNA saytının öz API sorğularını istifadə edir (`/api/bus/getBusList`, `/api/bus/getBusById`); backend işləyərkən AYNA-ya sorğu göndərilmir.

### 2.1) Brauzer demo səhifəsi (veb)

Backend ayağa qalxandan sonra brauzerdə **http://localhost:8000/** açın (`/web/`): sərnişin, operator və demo idarəetməsi tabları.
Bu səhifə sadə HTML/JS-dir (React/Vite yoxdur), eyni REST API-dən istifadə edir, xəritə OpenStreetMap + Leaflet-dir (atribusiya görünür;
Leaflet `backend/app/web/vendor/leaflet/` altında lokal saxlanılır, BSD-2). **Mobil Flutter tətbiqinin əvəzi deyil**, yalnız Flutter olmayan kompüterdə nümayiş üçündür.
Kodu dəyişəndən sonra: `docker compose up --build -d`.

### 3) Flutter tətbiqi (ayrıca işlədilir)

Tələblər: Flutter SDK (Dart ≥ 3.3). **iOS build və simulator yoxlaması üçün macOS + Xcode lazımdır.**

```bash
cd mobile
# Platforma qovluqlarını yarat (repoda yoxdur, çünki generasiya SDK tələb edir):
flutter create --platforms=android,ios --org az.bakuflow --project-name bakuflow_mobile .
# Əgər flutter test/widget_test.dart yaratdısa, silin (bu tətbiqə aid deyil).
python3 tool/apply_dev_platform_config.py   # yalnız İNKİŞAF üçün HTTP icazələri (aşağıya bax)
flutter pub get
flutter analyze && flutter test
```

`API_BASE_URL` yalnız build zamanı `--dart-define` ilə verilir (tətbiqə heç bir məxfi məlumat daxil edilmir):

| Hədəf | Əmr |
|---|---|
| **Android emulator** (host maşın = `10.0.2.2`) | `flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000` |
| **iOS simulator** (macOS) | `flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000` |
| **Fiziki telefon** (eyni Wi-Fi; kompüterin lokal IP-si) | `flutter run --dart-define=API_BASE_URL=http://192.168.X.Y:8000` |
| Android fiziki telefon, USB | `adb reverse tcp:8000 tcp:8000` sonra `http://127.0.0.1:8000` |

Fiziki telefon üçün: kompüterin IP-si (`ipconfig` / `ifconfig`), firewall-da 8000 portu açıq olmalıdır; iOS ilk dəfə lokal şəbəkə icazəsi soruşacaq.

**Lokal HTTP (yalnız development):** Android 9+ və iOS düz HTTP-ni bloklayır. `tool/apply_dev_platform_config.py` bunları əlavə edir:
Android `debug` manifestdə `usesCleartextTraffic=true` (release build-ə düşmür; main manifestə yalnız `INTERNET` icazəsi),
iOS `Info.plist`-ə `NSAllowsLocalNetworking`. **Production üçün API HTTPS olmalıdır** və iOS-dakı `NSAppTransportSecurity` bloku silinməlidir.

Xəritə OpenStreetMap plitələridir (ekranda mənbə atribusiyası var). Plitələr yüklənməsə siyahılar, ETA və bildirişlər işləməyə davam edir.
OSM-in ictimai plitə serveri yalnız yüngül/demo istifadə üçündür; real yükdə öz plitə provayderinizi istifadə edin.

### 4) Testlər (backend)

```bash
cd backend && pip install -r requirements-dev.txt
# Ayrıca baza (adı MÜTLƏQ "_test" ilə bitməlidir: testlər cədvəlləri təmizləyir):
docker compose exec db createdb -U bakuflow bakuflow_test
export TEST_DATABASE_URL=postgresql+psycopg://bakuflow:PAROL@127.0.0.1:5433/bakuflow_test
pytest -q
```

Testlər real CSV əvəzinə `tests/synth.py`-dakı **sintetik** 3600 sətirlik faylı (real formatla) istifadə edir.

## Demo ssenarisi və 2 dəqiqəlik təqdimat

Operator → **Demo** tabında ssenarilər: *Normal hərəkət*, *Qruplaşmış avtobuslar*, *Yol ləngiməsi*,
*10 dəqiqə davam edən yüksək sıxlıq*, (əlavə) *Qeyri-adi dayanma*, *Demo sıfırla*. Hər ssenari əvvəlki ~11–15 dəqiqənin GPS və
bildirişlərini yaradır və **real analiz kodundan keçirir**; qayda qısaldılmır. `high_crowd` ssenarisində demo bildirişləri
açıq `demo_seed` işarəsi ilə təzələnir ki, nümayiş zamanı məlumat köhnəlməsin.

**2 dəqiqəlik ssenari:**

1. **(0:00–0:20) Problem.** "Pik saatda bəzi avtobuslar dolu, yollarda tıxac var; sərnişin görmür, operator isə datasız qərar verir." Real: dayanacaqlar və AYNA marşrut xətləri; simulyasiya: avtobuslar; tıxac: sərnişin bildirişləri.
2. **(0:20–0:55) Sərnişin.** *Sərnişin* → `11` yazın, marşrutu seçin → xətt və avtobuslar (marşrut nömrəsi ilə), ETA, sıxlıq (rəng + mətn + "məlumat yoxdur"). Bir avtobusa **"Yüksək"** bildirin → kart yenilənir; dərhal təkrar → 60 san limiti.
3. **(0:55–1:25) Tıxac.** "Yolda tıxac var — bildir" → xəttin üstündə yer → **Ağır**. Xətdə qırmızı hissə və **alternativ yol** (mavi qırıq xətt) görünür. *Operator* → "Yol tıxacı bildirişləri" və xəbərdarlıq; **"Təsdiq et"** basın.
4. **(1:25–1:50) Əsas qayda.** *Demo* → **"10 dəqiqə davam edən yüksək sıxlıq"** → operatorda **"Əlavə avtobus ehtiyatı ayrılmalıdır"**; sübut: 10+ dəq davamlılıq, əhatə, diaqnoz "tutum çatışmazlığı ehtimalı".
5. **(1:50–2:00) Dürüstlük və növbəti addım.** Real GPS, real trafik datası, autentifikasiya, sərnişin gediş datasetı və Flutter build hələ yoxdur (məhdudiyyətlər).

## Təhlükəsizlik və məhdudiyyətlər (açıq)

- **Operator və demo endpointləri autentifikasiyasızdır.** Flutter-dakı "Sərnişin/Operator" seçimi yalnız demo girişidir, icazə sistemi **deyil**. Paylaşılan serverdə `DEMO_ENDPOINTS_ENABLED=false` qoyun və operator endpointlərinin qarşısına autentifikasiya əlavə edin.
- **Saxtakarlıqdan müdafiə tam deyil.** Eyni anonim sessiyadan eyni avtobusa 60 saniyədə bir bildiriş qəbul edilir. Yeni sessiya id-si ilə bu keçilə bilər; istifadəçinin avtobusda olduğu yoxlanmır; IP əsaslı limit yoxdur. Bildiriş vaxtını yalnız backend təyin edir (client vaxt göndərə bilməz, `extra=forbid`).
- Sessiya id-si DB-də yalnız HMAC-SHA256 hash kimi saxlanılır; dəqiq şəxsi lokasiya saxlanmır.
- Sıxlıq 5 dəqiqəlik pəncərədə sadə orta baldır: az sayda bildiriş nəticəni asanlıqla dəyişir. Bu ML modeli deyil, izah edilə bilən qaydadır.
- ETA sxematik xətt üzrə cari sürətin ekstrapolyasiyasıdır; ləngimə/dayanma zamanı yanıltıcı ola bilər (dayanmış avtobus üçün ETA göstərilmir).
- Simulyator avtobusları dayanacaqda dayanmır (dwell yoxdur) və xəttin sonunda başa qayıdır; GPS səs-küyü modelləşdirilməyib.
- Analiz hər 5 san bütün demo xətlər üzrə son ~30 dəq GPS-i yaddaşa yükləyir: demo miqyası üçün kifayətdir, real şəbəkə üçün optimallaşdırma tələb olunur.
- Tək backend prosesi nəzərdə tutulub (simulyator dövrü advisory lock ilə qorunur, lakin çoxlu worker lazımsızdır).

## Yoxlama statusu (faktiki nə işlədilib)

**İşlədilib və keçib** (Linux, PostgreSQL 16, Python 3.13):
- Backend: **97 pytest testi** (CSV/AYNA importu, koordinat təmizləmə, çatışmayan dayanacağın AYNA-dan əlavəsi, 10 dəqiqə qaydası, ssenarilər, bildiriş limitləri, tıxac klasterləşməsi/səviyyə/xəbərdarlıq/operator qərarı, demo) + alternativ yol seçimi üçün Node testi. Əsas testlər mutasiya ilə yoxlanıb.
- Alembic `upgrade → downgrade → upgrade`; real `uvicorn` ilə canlı tick dövrü.
- Veb interfeys Chromium (Playwright) ilə yoxlanıb: marşrut axtarışı, tıxac bildirmə, 429 limiti, operatorda tıxac kartı və xəbərdarlıq, mobil (390 px) görünüşü. OSRM-in real cavabı brauzerdə yoxlanıb; tam axın (tıxac → OSRM → xəritə) OSRM saxta cavabı ilə sınanıb.
- İstifadəçinin kompüterində: `docker compose up --build`, `import-routes` (198 marşrut), `seed-demo`.

**İşlədilməyib — özünüz yoxlayın:**
- **Flutter** (`mobile/`): heç vaxt kompilyasiya olunmayıb (`flutter analyze/test/build` yox), tıxac funksiyasını əhatə etmir, "Demo A/B" etiketləri qalıb. İşləyən interfeys veb səhifədir.
- Operator "Təsdiq et / Yalan bildiriş" düymələri brauzerdə sınanmayıb (yalnız API testi).
- Telefonda real açılış (PWA), Render/bulud yerləşdirmə.
- Sərnişin gediş datasetı inteqrasiya olunmayıb; marşrut 144 və 9 marşrut (AYNA-da dayanacaq məlumatı yoxdur) yoxdur.

## Yol tıxacı və alternativ yol

- Sərnişin avtobus nömrəsini yazıb marşrutu seçir, xətt xəritədə çıxır; **"Yolda tıxac var — bildir"** düyməsi ilə xəttin üstündə yeri seçib Yüngül/Orta/Ağır bildirir (`POST /api/traffic-reports`; nöqtə xəttə proyeksiya olunur, xəttdən >150 m uzaqdırsa rədd edilir; eyni sessiya + istiqamət üçün 60 san limit).
- Tıxac səviyyəsi **yalnız sərnişin bildirişlərindən** hesablanır (son 15 dəq; eyni sessiyanın yalnız son bildirişi sayılır; 400 m-dən yaxın bildirişlər bir tıxac sayılır). Real trafik sensoru/Waze/Google datası YOXDUR (açar/lisenziya tələb edir). 2 nəfərdən az bildiriş **"təsdiqlənməyib"** sayılır.
- **Ağır bildiriş (orta bal ≥ 2.4)** operatora dərhal `TRAFFIC_JAM` xəbərdarlığı kimi düşür (1 nəfər: "təsdiqlənməyib" başlığı; ≥2 nəfər: təsdiqlənmiş). Operator tabında "Yol tıxacı bildirişləri" kartı bütün marşrutları (avtobus simulyasiyası olmayanları da) göstərir. Şərt itəndə (15 dəq) xəbərdarlıq avtomatik həll olunur.
- **Operator qərarı:** xəbərdarlığın altında **"Təsdiq et"** (başlıq "operator təsdiq etdi" olur, yeni bildirişlərdə qalır) və tıxac üçün **"Yalan bildiriş (sil)"** (xəbərdarlıq bağlanır, istiqamətin sərnişin tıxac bildirişləri silinir) — `POST /api/operator/alerts/{id}/action`. Operator endpointləri autentifikasiyasızdır (prototip).
- **Alternativ yol**: orta/ağır tıxac olduqda brauzer OSRM (router.project-osrm.org, ictimai demo server) ilə tıxacdan yan keçən yol axtarır (əvvəl OSRM alternativləri, tapılmasa tıxacın hər iki yanından 450 m kənar ara nöqtə ilə) və xəritədə mavi qırıq xətt kimi göstərir; təsirlənən dayanacaqlar siyahılanır. OSRM canlı tıxacı bilmir; müddət tıxacsız şəraitdə hesablanır; yol təklifdir, marşrut dəyişikliyi operator qərarıdır. Xidmət əlçatan deyilsə tıxac məlumatı yenə göstərilir.
- Demo: sərnişin ekranında "Demo: tıxac simulyasiyası" (etiketli `demo_seed` bildirişlər).
- Miqrasiya: `alembic upgrade head` (0003; Docker başlayanda avtomatik).

## Telefonda tətbiq kimi açmaq (PWA)

Eyni Wi-Fi şəbəkəsində telefonun brauzerində `http://<kompüterin-IP>:8000/` açın (Windows-da IP: `ipconfig`; firewall icazə istəsə "Allow" edin). Chrome menyusundan "Add to Home screen" seçilsə, BakuFlow ikonu ilə tətbiq kimi açılır. Qeyd: bu veb tətbiqdir (PWA); Flutter kodu (`mobile/`) bu mühitdə heç vaxt kompilyasiya edilməyib və tıxac funksiyasını əhatə etmir.

## Render-də yerləşdirmə

Render → **New → Blueprint** → bu GitHub repo-su (`render.yaml` backend-i Docker kimi və PostgreSQL-i yaradır). İlk başlanğıcda `app.cli bootstrap` boş bazanı `ayna_routes.json` ilə (198 marşrut, AYNA dayanacaqları) doldurur və "normal" ssenarini qurur; təkrar başlayanda keçir. `DATABASE_URL` (`postgres://...`) avtomatik `postgresql+psycopg://` formasına çevrilir. Pulsuz planda sayt 15 dəq boş qalanda yatır (ilk açılış ~1 dəq), pulsuz PostgreSQL 30 gündən sonra silinir. Yerli (Docker Compose) işə salma bu yerləşdirmədən asılı deyil.
