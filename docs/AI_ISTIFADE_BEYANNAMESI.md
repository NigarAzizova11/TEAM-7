# AI istifadəsi haqqında bəyannamə — BakuFlow (Team 7)

> Bu sənəd layihədə süni intellektdən necə istifadə olunduğunu açıq şəkildə göstərir. Burada "AI" dedikdə **Claude** nəzərdə tutulur. Sənəddə yalnız faktiki baş verənlər qeyd olunub. Üçüncü bölmədəki promptlar komandanın söhbət zamanı yazdığı real tapşırıqların mənası dəyişdirilmədən ədəbi dildə yenidən ifadə olunmuş formasıdır.

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

## 3. Əsas promptlar

Aşağıdakı tapşırıqlar Claude-a Azərbaycan dilində verilmişdir. Burada onların məzmunu saxlanılmaqla ədəbi dildə təqdim olunur.

1. **İlkin tapşırıq.** Hackathonun problem bəyanatı, "BakuFlow" layihəsinin təsviri və texniki arxitektura tələbləri təqdim edilmiş, bu tələblərə uyğun tam işləyən prototipin hazırlanması istənilmişdir.
2. **Məlumat mənbəyi.** Komanda dayanacaq məlumatlarının yalnız CSV formatında deyil, həm də API vasitəsilə əldə oluna biləcəyini bildirmiş və bu məlumatların layihəyə necə daxil edilməsini soruşmuşdur.
3. **Real marşrutlar.** Yaxın dayanacaqların bir-birinə birləşdirilməsi ilə marşrut qurulmasının düzgün olmadığı qeyd edilmiş, marşrutların real məlumatının map.ayna.gov.az saytından əldə edilməsi tələb olunmuşdur.
4. **Marşrut xətlərinin yüklənməsi.** AYNA saytından hər marşrutun xəttinin və dayanacaq ardıcıllığının götürülməsi, bu məlumatın layihəyə inteqrasiyası istənilmişdir.
5. **Veb interfeys.** Swagger sənədləşməsi əvəzinə istifadəçinin brauzerdə baxa biləcəyi veb səhifənin hazırlanması tələb olunmuşdur.
6. **Avtobus və tıxac funksiyası.** Simulyasiya olunan avtobusların çıxarılması, real marşrut xəttinin saxlanması, sərnişin üçün avtobus adının göstərilməsi, marşrut xəttində tıxac olduqda alternativ yolun təklif edilməsi, tıxacın səviyyəsinin göstərilməsi və tıxac çox olduqda operatora xəbərdarlıq göndərilməsi istənilmişdir. Claude-un saxta avtobusların silinməsinin ETA və analiz funksiyalarını da aradan qaldıracağına dair sualına komanda avtobusların saxlanılması, yalnız onların adının dəyişdirilməsi qərarını vermişdir.
7. **Tıxac məlumatının mənbəyi.** Komanda Waze tətbiqində olduğu kimi yollardakı tıxacın göstərilməsini istəmişdir. Waze-in real datası açıq olmadığı üçün Claude tıxacın sərnişin bildirişlərinə əsasən müəyyən edilməsini (icma prinsipi) təklif etmişdir.
8. **Operator qərarı.** Operatorun xəbərdarlığı hansı addımla təsdiq edə biləcəyi soruşulmuş, bunun nəticəsində "Təsdiq et" və "Yalan bildiriş" əməliyyatları əlavə olunmuşdur.
9. **İstifadə rahatlığı və dizayn.** İnterfeysin anlaşılmaz olduğu, şriftin bəyənilmədiyi bildirilmiş, istifadə qaydasının sadələşdirilməsi və yeni şriftin tətbiqi tələb olunmuşdur.
10. **Yerləşdirmə və sənədləşmə.** GitHub repozitoriyasının hazırlanması, Render platformasında yerləşdirmə, həmçinin AI istifadəsi bəyannaməsi və texniki izah sənədinin yazılması istənilmişdir.

## 4. AI nəticələrinin yoxlanması

- 99 avtomatik test + mutasiya testləri (README → "Yoxlama statusu").
- Interfeys Chromium ilə (Playwright) real PostgreSQL üzərində yoxlanıb: marşrut axtarışı, tıxac bildirmə, 60 saniyə limiti, operator kartı, mobil görünüş.
- OSRM-in real cavabı brauzerdə yoxlanıb.
- Komanda öz kompüterində `docker compose up`, `import-routes` və səhifəni işlədib.
- AI-nin ilk yazdığı bəzi səhvlər tapılıb və düzəldilib (məsələn, simulyator avtobusları real xətt əvəzinə dayanacaqları birləşdirən xətlə hərəkət etdirirdi və yalan "yol ləngiməsi" xəbərdarlığı yaranırdı).
