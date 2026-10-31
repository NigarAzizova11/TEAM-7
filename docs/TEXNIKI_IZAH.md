# BakuFlow — Texniki izah sənədi (Team 7)

## 1. Həll etdiyimiz problem

Pik saatda Bakı avtobuslarının bəziləri dolu olur, arxasınca gələnlər isə boş. Sərnişin sıxlığı görmür; operator isə **"əlavə avtobus lazımdır, yoxsa mövcud avtobusların intervalını düzəltmək kifayətdir?"** sualına datasız cavab verir. Yollardakı tıxac da gecikmənin əsas səbəbidir, amma sərnişin və operator bunu avtobus xəttinə bağlı görmür.

BakuFlow bu üç şeyi birləşdirir: **real marşrut xətləri**, **sərnişin bildirişləri (sıxlıq və tıxac)** və **operator üçün izah edilə bilən xəbərdarlıqlar** (hadisə, mümkün səbəb, ölçülmüş sübut, tövsiyə).

## 2. Nə edir (funksiyalar)

**Sərnişin:** avtobus nömrəsini yazır → marşrutu/istiqaməti/dayanacağı seçir → xəritədə real xətt və dayanacaqlar; yaxınlaşan avtobuslar, ETA, sıxlıq (rəng + mətn; "məlumat yoxdur" heç vaxt "aşağı" sayılmır); 3 düymə ilə sıxlıq bildirişi; daha boş növbəti avtobus təklifi; **xəttin üstündə tıxac bildirişi** (Yüngül/Orta/Ağır), tıxac səviyyəsi xətdə rənglə, **alternativ yol** təklifi (mavi qırıq xətt).

**Operator:** marşrut cədvəli (sıxlıq, məlumatın yeniliyi, intervallar, aktiv avtobuslar, tıxac), xəbərdarlıqlar (hadisə / səbəb / sübut / tövsiyə / vaxt / vəziyyət), tıxac bildirişləri kartı, **"Təsdiq et" və "Yalan bildiriş"** düymələri, demo idarəetmə paneli.

**Məcburi qayda:** 10 dəqiqə fasiləsiz yüksək xətt sıxlığı → **"Əlavə avtobus ehtiyatı ayrılmalıdır"**. Əlavə analizlər: avtobus qruplaşması (bunching), mümkün yol ləngiməsi, qeyri-adi dayanma, tutum çatışmazlığı diaqnozu.

## 3. Texnologiyalar və seçim səbəbləri

| Qat | Seçim | Niyə |
|---|---|---|
| Backend | Python **FastAPI** | Tapşırıqda məcburi; sürətli REST, avtomatik sənədləşmə |
| Verilənlər bazası | **PostgreSQL 16** (SQLite yox) | Tapşırıqda məcburi; qismən unikal indeks (aktiv xəbərdarlığın təkrarlanmaması), JSONB (xətt geometriyası), advisory lock (simulyator dövrünün təkliyi) |
| ORM/miqrasiya | **SQLAlchemy 2.x**, **Alembic** (0001–0003) | Tapşırıqda məcburi; miqrasiyanın özü testlərdə sıfırdan yoxlanır |
| Xəritə | **Leaflet + OpenStreetMap** (veb), flutter_map (mobil kod) | OSM atributiyası ilə, açıq lisenziya; Leaflet lokal saxlanılır |
| Interfeys | Sadə HTML/JS (veb), PWA | Quraşdırma tələb etmir; telefonda "Add to Home screen" |
| Mobil | Flutter kodu (`mobile/`) | Tapşırıq tələbi; **hələ kompilyasiya edilməyib** |
| Real-vaxt | REST + **5 saniyəlik polling** (səhifə gizli olanda dayanır) | Tapşırıq tələbi: WebSocket yox |
| Yerləşdirmə | **Docker Compose** (backend + DB), Render Blueprint (`render.yaml`) | Tək əmrlə qalxır; `API_BASE_URL` dəyişəni |
| Alternativ yol | **OSRM** ictimai demo serveri | Açarsız, pulsuz marşrutlaşdırma |
| Məlumat | AYNA saytının açıq API cavabı + dayanacaq CSV-si | Real xətt və dayanacaq ardıcıllığı |

## 4. Layihənin strukturu

```
bakuflow/
├── docker-compose.yml        # db (PostgreSQL 16) + backend
├── render.yaml               # Render Blueprint
├── README.md                 # işə salma, real/simulyasiya cədvəli, yoxlama statusu
├── docs/                     # bu sənəd və AI bəyannaməsi
├── backend/
│   ├── Dockerfile, requirements*.txt, alembic/ (miqrasiyalar 0001–0003)
│   ├── data/ayna_routes.json # 199 marşrut: xətt + dayanacaq ardıcıllığı + dayanacaq adı/koordinatı
│   ├── tools/                # AYNA-dan məlumat çıxaran skriptlər (Python və brauzer JS)
│   ├── app/
│   │   ├── main.py, config.py, db.py, models.py, schemas.py, clock.py, geo.py
│   │   ├── routers/          # passenger, operator, demo (REST)
│   │   ├── services/         # analysis, crowd, transit, simulator, traffic,
│   │   │                     # ayna_import, csv_import, views, reports, demo, ticker
│   │   └── web/              # index.html, detour.js, manifest.json, vendor/leaflet
│   └── tests/                # 99 pytest testi + Node testi
└── mobile/                   # Flutter mənbə kodu
```

## 5. Arxitektura

```
 Brauzer / Flutter ──REST (5 san polling)──► FastAPI ──► PostgreSQL
       │                                      │
       └── OSRM (alternativ yol, yalnız      ticker (hər 5 san): simulyator → analiz → xəbərdarlıqlar
           tıxac olduqda, brauzerdən)
```

Əsas qərarlar:
- **Sıxlıq xəttə bağlıdır** (marşrut + istiqamət). Avtobus sıxlığı sərnişin bildirişlərinin 5 dəqiqəlik orta balıdır; xətt nəticəsi üçün kifayət qədər avtobus əhatəsi tələb olunur, əks halda "məlumat yoxdur".
- **10 dəqiqəlik qayda vəziyyətsiz hesablanır:** hər an üçün keçmiş 10 dəqiqəni dəqiqə addımı ilə yenidən qiymətləndirir, saxlanmış "sayğac" yoxdur; xəbərdarlıq şərt itəndə həll olunur, yenidən yaranarsa yeni xəbərdarlıq açılır.
- **Aktiv xəbərdarlıq təkrarlanmır:** `dedup_key` üzərində PostgreSQL qismən unikal indeks.
- **Bildiriş vaxtını yalnız backend təyin edir** (client vaxt göndərə bilməz); sessiya id-si yalnız HMAC-hash kimi saxlanılır; eyni sessiya + eyni avtobus/istiqamət üçün 60 saniyə limit.
- **Real xətt:** AYNA xətti Douglas-Peucker ilə ~8 m dəqiqliyə sadələşdirilir; dayanacaqlar xətt boyunca **monoton** proyeksiya olunur (özünü kəsən/ora-bura xətlərdə qarışmasın deyə); GPS mövqeyi əvvəlki mövqeyə yaxın hissəyə üstünlük verən "hint" proyeksiya ilə tapılır.

## 6. Tıxac mexanizmi (indiki vəziyyət)

1. Sərnişin xəttin üstündə nöqtə seçir; server onu istiqamət xəttinə proyeksiya edir (xəttdən >150 m uzaqdırsa rədd).
2. Son 15 dəqiqənin bildirişləri (hər sessiyadan yalnız sonuncu) xətt boyunca sıralanır; **400 m-dən yaxın bildirişlər bir tıxac sayılır**, tıxacın başlanğıc/son məsafəsi (`from_m`–`to_m`) və mərkəzi hesablanır.
3. Səviyyə: orta bal < 1.7 yüngül, < 2.4 orta, ≥ 2.4 ağır; 2 nəfərdən az bildiriş "təsdiqlənməyib".
4. Ağır bildiriş operatora `TRAFFIC_JAM` xəbərdarlığı kimi düşür (1 nəfər: "təsdiqlənməyib"; ≥2: təsdiqlənmiş); operator təsdiq edə və ya yalan kimi silə bilər; şərt itəndə (15 dəq) xəbərdarlıq avtomatik həll olunur.
5. **Alternativ yol:** orta/ağır tıxac üçün tıxacdan 600 m əvvəl və sonra iki nöqtə götürülür; brauzer OSRM-dən alternativ yollar istəyir, tıxac nöqtəsindən yan keçəni seçir; tapılmasa tıxacın hər iki yanından 450 m kənar ara nöqtə ilə cəhd edir. Yol təsirləndirdiyi dayanacaqları da göstərir.

**Dürüst məhdudiyyət:** real trafik sensoru (Waze/Google/TomTom) yoxdur; tıxac yalnız sərnişin bildirişlərinə əsaslanır. OSRM canlı tıxacı bilmir, müddət tıxacsız şəraitdə hesablanır.

## 7. Real / simulyasiya cədvəli (qısa)

Real: dayanacaqlar, 198 marşrutun xətti və dayanacaq ardıcıllığı. Simulyasiya: avtobusların mövqeyi/GPS-i (12 marşrutda), demo sıxlıq bildirişləri. Sərnişin bildirişlərinə əsaslanan: tıxac. Tam cədvəl README-dədir.

## 8. Gələcək inkişaf imkanları

### 8.1 Tıxacı nöqtə yox, **xətt parçası (A nöqtəsindən B nöqtəsinə)** kimi bildirmək
İndi sərnişin bir nöqtə seçir, tıxacın uzunluğu bildirişlərin yayılmasından çıxarılır. Növbəti addım:
- Sərnişin xəttdə **iki nöqtə** seçir: tıxacın başlanğıcı (A) və sonu (B). Bildiriş `d_from`/`d_to` ilə saxlanılır (cədvəl sahələri əlavə olunur).
- Parça xəritədə dəqiq A→B rənglənir; hər parça üçün **tıxac uzunluğu** (m) və təxmini **gecikmə** hesablanır.
- Üst-üstə düşən parçalar birləşdirilir, bir neçə sərnişinin A/B nöqtələrinin medianı götürülür (səs-küyə davamlı).
- Alternativ yol birbaşa A-dan əvvəlki və B-dən sonrakı nöqtələr üçün qurulur (indikindən daha dəqiq).

### 8.2 Sərnişinin **canlı mövqeyi** (saytda)
- Brauzer Geolocation API ilə (istifadəçi icazəsi ilə, opt-in) sərnişinin yeri xəritədə göstərilir.
- Mövqe seçilmiş istiqamətin xəttinə proyeksiya olunur: "ən yaxın dayanacaq", "xəttdən məsafə", avtobusa çatma ETA-sı avtomatik.
- **Tıxac bildirişi bir toxunuşla:** sərnişin avtobusda gedirsə və sürəti çox aşağıdırsa, tətbiq "Burada tıxac var?" soruşur, nöqtəni əl ilə seçməyə ehtiyac qalmır; ardıcıl GPS izindən parçanın A və B nöqtələri avtomatik çıxarılır.
- **Saxtakarlığa qarşı:** bildirişin xəttə yaxın mövqedən göndərildiyi yoxlanılır (indi yoxlanılmır).
- Məxfilik: dəqiq mövqe saxlanmır, yalnız xəttdəki məsafə və vaxt; icazə istənilən vaxt geri alına bilər. Mobil tətbiqdə arxa plan konumu ayrıca icazə tələb edir.

### 8.3 Digər istiqamətlər
- **Real GPS** inteqrasiyası (Bakı Nəqliyyat Agentliyi/AYNA ilə) — simulyatoru əvəz edir, analiz mühərriki dəyişmir.
- **Real trafik datası** (TomTom/HERE/Waze for Cities) ilə sərnişin bildirişlərinin birləşdirilməsi və çarpaz yoxlanması.
- Sərnişin gediş datasetinin (`bakubus_passenger-2026.csv`) **marşrut səviyyəsində tarixi yük** kimi qoşulması (dayanacaq səviyyəsində deyil, real-vaxt deyil — açıq işarələnməklə).
- Autentifikasiya və rol sistemi (operator endpointləri indi açıqdır), IP/cihaz əsaslı sui-istifadə limiti.
- Flutter tətbiqinin kompilyasiyası, tıxac və canlı mövqe ekranlarının əlavə olunması, push bildirişlər.
- Proqnozlaşdırma (qısamüddətli sıxlıq/gecikmə) — hələlik izah edilə bilən qaydalar, ML yoxdur; kifayət qədər tarixi data toplanandan sonra.
- Çoxlu worker üçün simulyator/analiz yükünün ayrıca xidmətə çıxarılması, analiz yükünün optimallaşdırılması.
