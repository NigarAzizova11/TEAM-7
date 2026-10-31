# AI istifadəsi haqqında bəyannamə — BakuFlow (Team 7)

> Bu sənəd layihədə süni intellektdən necə istifadə olunduğunu açıq göstərir. Aşağıda "AI" dedikdə **Claude** nəzərdə tutulur. Bəyannamədə yalnız faktiki baş verənlər yazılıb; verbatim prompt kimi göstərilən mətnlər komandanın söhbətdə yazdığı real mesajlardır (orfoqrafiya olduğu kimi saxlanılıb, qısaldılıb).

## 1. İstifadə olunan AI alətləri

| Alət | Harada, nə üçün |
|---|---|
| **Claude (Anthropic)**, model `claude-sonnet-5-5`, Claude Code əsaslı agent rejimi (Claude masaüstü tətbiqi vasitəsilə) | Bütün layihənin kodu, testləri, miqrasiyalar, README və bu sənədlər; arxitektura variantlarının müzakirəsi; verilənlərin AYNA saytından çıxarılması üçün skriptlər; səhvlərin diaqnostikası |
| Claude-un alətləri: Linux iş mühiti (Python, PostgreSQL 16, Node, Chromium/Playwright), kompüterdə qovluğa yazma, brauzer paneli | Kodun işə salınması, `pytest`-in işlədilməsi, interfeysin brauzerdə yoxlanması, AYNA API cavabının brauzer vasitəsilə götürülməsi |
| *(Komanda doldursun)* Başqa AI alətləri (ChatGPT, Gemini və s.) | Bu sənədi hazırlayan zaman bu alətlərin istifadəsi mənə məlum deyil. İstifadə olunubsa, burada göstərin: alət, məqsəd, nə qədər |

AI-nin **işləmədiyi** yerlər: dizayn qərarlarının son təsdiqi, tapşırığın şərtləri, real məlumatların (AYNA, dayanacaq CSV-si) mənbəyinin seçilməsi, Docker-in və GitHub/Render-in öz hesablarımızda işə salınması, nəticələrin brauzerdə baxılıb qəbul edilməsi.

## 2. Hansı mərhələdə AI nə etdi

**Arxitektura seçimi.** Tapşırıqda məcburi texnologiyalar verilmişdi (FastAPI + PostgreSQL + SQLAlchemy + Alembic, Flutter, flutter_map/OSM, yalnız REST, 5 saniyəlik polling, Docker Compose). AI bunların daxilində qərarlar təklif etdi: sıxlığın avtobusa yox xəttə (marşrut + istiqamət) bağlı qaydası, 10 dəqiqəlik qaydanın "vəziyyətsiz" (stateless) hesablanması, aktiv xəbərdarlığın təkrarlanmaması üçün PostgreSQL qismən unikal indeksi, vahid saat modulu. Bu variantlar komanda ilə müzakirə edilib qəbul edildi.

**Kod.** Backend (FastAPI, modellər, xidmətlər, CLI), analiz mühərriki (sıxlıq, 10 dəqiqə qaydası, qruplaşma, yol ləngiməsi, qeyri-adi dayanma, tutum diaqnozu), AYNA idxalçısı, tıxac modulu, veb interfeys (`backend/app/web`), alternativ yol seçimi (`detour.js`), Render üçün `render.yaml` və `bootstrap` AI tərəfindən yazılıb. Flutter mənbə kodu da AI tərəfindən yazılıb, amma **heç vaxt kompilyasiya olunmayıb** (README-də qeyd var).

**Testlər.** AI 99 pytest testi yazdı (CSV/AYNA importu, 10 dəqiqə qaydası, ssenarilər, bildiriş limitləri, tıxac, operator qərarı və s.) və alternativ yol seçimi üçün Node testi. Əsas testlər **mutasiya ilə yoxlandı**: kod qəsdən pozulur, müvafiq testin uğursuz olması yoxlanır. Bu yoxlamalar zamanı real boşluqlar tapıldı (məsələn, "eyni sessiya bir dəfə sayılır" və "2 nəfərlik bildiriş" halları əvvəl testlə örtülməmişdi, əlavə edildi).

**Məlumat.** AYNA marşrutları (xətt, dayanacaq ardıcıllığı) map.ayna.gov.az saytının öz API cavabından brauzer vasitəsilə götürüldü. AI skripti yazdı və işlətdi; komanda saytı və məqsədi göstərdi.

## 3. Əsas promptlar (komandanın real mesajlarından)

Prompt mətnləri Azərbaycan dilindədir. Aşağıda yönləndirici olanlar:

1. **İlkin tapşırıq:** hackathon problem bəyanatı, "BakuFlow" prompt sənədi və texniki arxitektura tələbləri (tam mətn layihənin başlanğıc söhbətində verilib).
2. **Kimi məlumat lazımdır:** *"MENDE ONUN API YI VAR JSON ONLARI AT BERKE CSV ATSAM CETIN OLACAQ"* — komanda real dayanacaq məlumatı barədə.
3. **Düzgün marşrutlar:** *"BAX sen sehv elemisen bi birine yaxn dayanacaqlari birlesdirmewk duzgun deyil . esas men sene sayt atacam hemin saytda bax ordan lazmli melumati fetch edek"* — bu mesajdan sonra uydurma demo marşrutlar kənarlaşdırıldı, real AYNA marşrutlarına keçildi.
4. *"men sene linki atdm ki ordan data ni cekesen her marsrutun xettini goturesen onu eledin?"* — 198 marşrutun xəttinin götürülməsi.
5. **Veb interfeys:** *"yoxe men WEB SAYTA BAXANMRAM"* — Swagger əvəzinə baxıla bilən sayt.
6. **Saxta avtobuslar:** *"SAXTALARI VSIL ESL AVTOBUS XETTI QALSN HEMCININ SERNISIN UCN AVTOBUS ADI OLSUN ... TIXAC VARSA ONUN ALTERNATV GEDIS YOLU TEKLF OLUNSUN ... TIXAC COXDURSA OPERATORA XEBERDARLIQ GETMELIDIR* — tıxac, alternativ yol və operator xəbərdarlığı funksiyalarının mənbəyi. AI-nin sualına (saxta avtobusların silinməsi ETA və analizi də itirir) komanda "avtobuslar qalsın, yalnız adı dəyişsin" cavabını verdi.
7. **Tıxac mənbəyi:** *"DEYESEN WAZE PROQRAMNDA YOLLDARDAKI TIXAC GORSENRDI"* — Waze-in real datası açıq olmadığı üçün AI tıxacı sərnişin bildirişlərindən (icma prinsipi) hesablamağı təklif etdi.
8. **Operator qərarı:** *"operator hardan tesdiqesin"* — operatorun "Təsdiq et / Yalan bildiriş" düymələri.
9. **Dizayn:** *"bax istifadesi ve interface designi yaxsi deyil basa dusulmur yeni hem adi herflerin fontuunu bele beyenmemisem..."* — təlimat, nömrələnmiş addımlar, yeni şrift.
10. **Yerləşdirmə:** *"render edek indi"*, GitHub reposu və bu sənədlər üçün mesajlar.

## 4. AI nəticələrinin yoxlanması

- 99 avtomatik test + mutasiya testləri (README → "Yoxlama statusu").
- Interfeys Chromium ilə (Playwright) real PostgreSQL üzərində yoxlanıb: marşrut axtarışı, tıxac bildirmə, 60 saniyə limiti, operator kartı, mobil görünüş.
- OSRM-in real cavabı brauzerdə yoxlanıb.
- Komanda öz kompüterində `docker compose up`, `import-routes` və səhifəni işlədib.
- AI-nin ilk yazdığı bəzi səhvlər tapılıb və düzəldilib (məsələn, simulyator avtobusları real xətt əvəzinə dayanacaqları birləşdirən xətlə hərəkət etdirirdi və yalan "yol ləngiməsi" xəbərdarlığı yaranırdı).

## 5. Məhdudiyyətlər və qeydlər

- AI-nin yazdığı kod **tam insan audit sinfindən keçməyib**; Flutter kodu kompilyasiya olunmayıb; operator düymələri brauzerdə əl ilə sınanmayıb; Render yerləşdirməsi və telefonda PWA yoxlanmayıb.
- Üçüncü tərəf resurslar: OpenStreetMap lövhələri, Leaflet (lokal), Inter şrifti (Google Fonts), OSRM ictimai demo serveri, AYNA saytının açıq API cavabları.
- Sistem simulyasiya olunan hissələri (avtobus mövqeyi, demo bildirişlər) UI-da və README-də açıq işarələyir; real/simulyasiya cədvəli README-dədir.
