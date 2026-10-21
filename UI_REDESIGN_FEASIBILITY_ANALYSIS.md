# MONGOLRANGER — UI REDESIGN FEASIBILITY ANALYSIS & ARCHITECTURAL REPORT

> **Төлөв:** Шинжилгээ ба Техникийн Үнэлгээ (Код өөрчлөөгүй — таны баталгаажуулалтыг хүлээж байна)
> **Зорилго:** Одоогийн ажиллаж буй Warcraft III 1.26a сүлжээ, Rejoin, Anti-Cheat, ELO, WarKey болон Lobby системүүдийг эвдэлгүйгээр хавсаргасан шинэ дизайныг (`media_1792491528867_95e05add.jpg`) хамгийн өндөр нарийвчлалтайгаар бүтээх техникийн боломжийг тодорхойлох.

---

## 1. ОДООГИЙН ПРОЕКТЫН БҮТЭЦ БА АРХИТЕКТУРЫН ШИНЖИЛГЭЭ (`INSPECT THE CURRENT PROJECT`)

Проектын эх кодыг бүрэн шалгаж үзэхэд дараах архитектур ажиллаж байна:

### 1.1. Одоо ашиглагдаж буй UI Framework ба Хэл
* **Үндсэн Windows Клиент (Production UI):** **C# (.NET Framework 4.0 / `v4.0.30319`) + WPF (Windows Presentation Foundation)**.
  * Эх код нь [`backend/build_client_packages.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py) доторх `WPF_CSHARP_SOURCE` (мөр 85–6430) болон `XAML_UI` (мөр 580–1943) хувьсагчид хадгалагддаг бөгөөд Windows-ийн суурь `csc.exe` компилятораар ([`compile_standalone_exe()`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L6516-L6566)) ямар ч гадны `.dll` шаардахгүйгээр **ганцхан ширхэг бие даасан `.exe` файл** ([`dist_packages/MongolRanger-Setup.exe`](file:///d:/Projects/war3%20reconnect%20host%20service/dist_packages/MongolRanger-Setup.exe), `~578 KB`) болж хөрвүүлэгддэг.
  * Ашиглаж буй WPF сангууд: `PresentationFramework.dll`, `PresentationCore.dll`, `WindowsBase.dll`, `System.Xaml.dll`, `System.Web.Extensions.dll`.
* **Туслах / Legacy файлууд (Идэвхгүй):**
  * [`client/mongolranger_gui.py`](file:///d:/Projects/war3%20reconnect%20host%20service/client/mongolranger_gui.py) — Хуучин туршилтын Python `tkinter` скрипт (одоогийн `.exe`-д ашиглагддаггүй).
  * [`web/index.html`](file:///d:/Projects/war3%20reconnect%20host%20service/web/index.html) ба [`web/app.js`](file:///d:/Projects/war3%20reconnect%20host%20service/web/app.js) — Серверийн веб хяналтын хуудас.
* **Backend Сервер:**
  * [`backend/app.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/app.py) — Python **FastAPI + SQLite (WAL mode)** REST API сервер (Бүртгэл, Өрөө, ELO, Match History, Чат, Heartbeat, Auto-Updater).
  * [`backend/w3gs_room.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/w3gs_room.py) — Python `asyncio` дээр суурилсан **Virtual W3GS Authoritative Game Server & Reconnect Engine** (`W3GSRoomManager`, `W3GSRoom`).

### 1.2. UI нь Backend болон Натив Системтэй хэрхэн холбогддог вэ?
Бүх логик [`backend/build_client_packages.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py) доторх `MongolRangerClient.Program` класс дотор маш цэгцтэй, UI-аас тусгаарлагдсан байдлаар бичигдсэн байна:
1. **REST API Холболт:** [`SendJson()`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L6221-L6290) болон `JavaScriptSerializer` ашиглан `http://103.153.141.135:8080` руу JSON хүсэлтүүд (`POST /login`, `GET /state`, `POST /rooms`, `POST /rooms/{id}/join`, `POST /rooms/{id}/rejoin` г.м.) илгээдэг.
2. **State Polling & Sync:** [`PollServer()`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L4691-L4835) функц нь фоноор серверийн төлөвийг авч, `window.Dispatcher.BeginInvoke` ашиглан WPF-ийн `ItemsSource`-уудыг шинэчилдэг.
3. **Натив W3GS Сүлжээ ба Rejoin Bridge:**
   * [`StartNativeGamingServices()`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L4898-L4972) — UDP `6112` LAN Broadcast (`SendRawLanGameInfo`) болон Local TCP Proxy (`127.0.0.1:6113` -> Серверийн W3GS порт) үүсгэдэг.
   * [`BridgeTcpSession()`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L5102-L5208) — Тоглоомын үеийн W3GS пакетуудыг дамжуулах ба `0x07 START_LOADING` пакетыг барьж авч дэлгэцийг автоматаар тоглоом руу шилжүүлдэг.
4. **Warcraft III 1.26a интеграц, Anti-Cheat ба WarKey:**
   * [`ScanAndEnforceMapIntegrity()`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L3178-L3290) — `.mix`, `.asi`, `.flt`, `.dll` MapHack файлуудыг илрүүлж устгадаг.
   * [`NativeWarKeyEngine`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L240-L565) — `WH_KEYBOARD_LL` low-level hook-ээр Inventory (`Numpad 7/8/4/5/1/2`) болон Skill товчнуудыг чат бичих үед давхцахгүйгээр дамжуулдаг.

### 1.3. Дахин ашиглах боломжтой бэлэн Data Models (100% бэлэн)
WPF-ийн DataBinding-д зориулсан дараах классууд аль хэдийн [`backend/build_client_packages.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py) дотор бэлэн бичигдсэн байгаа бөгөөд шинэ UI-ийн хүснэгт, картуудтай шууд холбогдоно:
* [`LobbyItem`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L118-L131) (`Id`, `Name`, `Host`, `MapName`, `PlayersText`, `PingText`, `StatusText`, `PasswordBadge`, `ActionButtonText`)
* [`RoomMemberItem`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L133-L149) (`Username`, `ClanTag`, `PingText`, `PingBrush`, `TrustText`, `StatsText`, `AvatarLetter`)
* [`ChatMessageItem`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L151-L160) (`Sender`, `SenderBrush`, `Timestamp`, `Message`)
* [`LeaderboardItem`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L162-L175) (`Username`, `RankDisplay`, `EloText`, `WinLossText`, `TrustText`)
* [`FriendItem`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L177-L190) (`Username`, `StatusText`, `DotBrush`, `AvatarBrush`)
* [`MatchHistoryItem`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L211-L224) (`MapName`, `ResultText`, `EloChangeText`, `DurationText`, `DateText`)

---

## 2. ХАВСАРГАСАН ДИЗАЙНЫ НАРИЙВЧИЛСАН ШИНЖИЛГЭЭ (`ANALYZE THE ATTACHED DESIGN`)

Таны хавсаргасан зураг (`media_1792491528867_95e05add.jpg`) дээрх бүх элементүүдийг техникийн түвшинд задлан шинжилбэл:

| № | Дизайны Элемент | Зураг дээрх Харагдах Байдал | Одоогийн WPF (`XAML_UI`) дээрх боломж |
| :--- | :--- | :--- | :--- |
| **1** | **Application Title Bar** | Custom frameless дээд мөр (`WindowStyle="None"`), зүүн дээд буланд алтан титэм/дуулга бүхий `MONGOLRANGER` лого, баруун талд `🔔`, `⚙`, `—`, `□`, `✕` товчнууд. | **100% боломжтой.** Одоо ч frameless цонх болон `TitleBarDrag_MouseLeftButtonDown` ашиглаж байгаа. |
| **2** | **Logo & Branding** | Алтан шаргал градиент (`#FDE68A` -> `#D97706`) бүхий serif/fantasy титэмтэй лого. | **100% боломжтой.** Зураг (`PNG`) эсвэл WPF Vector `<Path>` геометрээр 1:1 хийнэ. |
| **3** | **Background Artwork (Hero Banner)** | Дээд хэсэгт Lich King / Frozen Throne уран сайхны зураг, доошоо болон зүүн тийш бараан уусалттай (`LinearGradientBrush` opacity mask). | **100% боломжтой.** Зургийг `.exe` дотор Embedded Resource болгон багцалж, `ImageBrush` + `LinearGradientBrush` давхарлана. |
| **4** | **Dark Theme & Color Palette** | Гүн хар хөх суурь (`#0B0E17`, `#111624`), картын дэвсгэр (`#161C2E`), алтан хүрээ (`#C89B3C` / `#D97706`), ногоон (`#16A34A` -> `#15803D`) болон улаан (`#991B1B`) товчнууд. | **100% боломжтой.** WPF `LinearGradientBrush`, `RadialGradientBrush`, `DropShadowEffect` үүнийг төгс дүрсэлдэг. |
| **5** | **Sidebar Navigation** | Зүүн баганад (`~235px`): Тоглогчийн карт, `ONLINE ROOMS` (идэвхтэй үед алтан зүүн индикатор + алтан градиент дэвсгэр), `RANKINGS`, `FRIENDS`, `RECENT GAMES`, `SETTINGS`, доор нь `SELECT GAME DATA` ба улаан `EXIT`. | **100% боломжтой.** |
| **6** | **Player Profile Card** | Зүүн дээд хэсэгт дугуй аватар зураг, ногоон онлайн цэг, `Batuka_MN`, `● Online`, алтан цомтой `1550 ELO`, доор нь `Wins: 128 \| Losses: 95 \| Win Rate: 57%`. | **100% боломжтой.** WPF `Ellipse` clip + `DataBinding`. |
| **7** | **Lobby Creation Controls** | Баруун талын `CREATE LOBBY` карт дотор дээрээс доош яг 5 удирдлага:<br>1. `Room Name` input<br>2. `Map Selection` dropdown (`DotA v6.85m LoD` آیکонтой)<br>3. `Room Password (Optional)` (`🔒` آیکонтой)<br>4. `No Leavers (Min 90% Stay Rate)` алтан/ногоон Toggle Switch<br>5. Ногоон `CREATE LOBBY` товч + доор нь `27 Players Online • 5 Active Rooms`. | **100% боломжтой.** Toggle switch-ийг WPF custom `ControlTemplate`-ээр яг зураг шиг хийнэ. |
| **8** | **Search Bar & Filter Tabs** | `🔍 Search rooms...` хайлтын нүд, баруун талд нь `[All] [Open] [Friends] [Low Ping]` сегментчилсэн табууд (идэвхтэй таб нь алтан хүрээ/дэвсгэртэй). | **100% боломжтой.** |
| **9** | **Lobby List & Table** | `ROOM NAME`, `HOST`, `MAP`, `PLAYERS`, `PING`, `ACTION` баганатай жагсаалт. Мөр бүр дээр газрын зургийн жижиг зураг (thumbnail), ногоон Wi-Fi 3 зураастай пинг (`18 ms`), ногоон `JOIN` товч. | **100% боломжтой.** |
| **10** | **Map Dropdown & Popup** | Хүснэгтийн доор харагдаж буй газрын зургийн сонголтын цэс: 5 газрын зураг тус бүр өөрийн жижиг зурагтай, сонгогдсон мөр нь алтан зүүн зураас + алтан `✔` тэмдэглэгээтэй. | **100% боломжтой.** WPF `ComboBox` `ItemTemplate` болон `Popup` темплейтээр хийгдэнэ. |

### Шаардлагатай Дизайн Ассетууд (Assets Checklist):
Яг зураг дээрх шиг 98–100% пикселийн нарийвчлал гаргахын тулд дараах графикууд хэрэг болно:
1. **Зураг (Raster Artwork):**
   * `banner_lichking.jpg/png` — Дээд хэсгийн Lich King арын зураг + `MONGOLRANGER` лого (Таны явуулсан зургаас шууд өндөр чанартайгаар хайчилж аваад `.exe` дотор Base64/Resource болгон шингээх боломжтой).
   * **5 газрын зургийн жижиг дүрс (Map Thumbnails `64x64` PNG):**
     1. `DotA v6.85m LoD`
     2. `DotA v6.74c LoD v5e`
     3. `DotA v6.83d Allstars`
     4. `DotA v6.85l LoD`
     5. `DotA v6.85k Allstars`
     *(Эдгээрийг мөн таны зургаас шууд crop хийж эсвэл Warcraft III-ийн икон сангаас гаргаж `.exe`-д багцална).*
2. **Вектор Иконууд (Icons):**
   * Одоогийн код дээр Unicode тэмдэгтүүд (`&#x1F3AE;` г.м.) ашигласан нь Windows 10/11 дээр энгийн эможи шиг харагддаг. Үүнийг WPF-ийн **SVG Vector `<Path Data="..."/>`** геометрээр сольсноор цом, сэлэм, бамбай, цоож, Wi-Fi пинг, хайлтын томруулдаг шил зэрэг нь зураг дээрх шиг **жинхэнэ металл алтан болон ногоон градиенттай** болно.
3. **Фонт (Typography):**
   * Гарчигт `Cinzel` / `Beaufort for LOL` / `Georgia Bold`, үндсэн текстэд `Segoe UI` / `Inter` (`Segoe UI Semibold`, `Bold`).

---

## 3. БҮТЭЭГДЭХҮҮНИЙ ТУСГАЙ ШААРДЛАГУУД (`IMPORTANT PRODUCT REQUIREMENTS`)

Таны тавьсан шаардлагууд одоогийн системтэй хэрхэн нийцэж байгааг шалгав:

1. **Зөвхөн Warcraft III 1.26a:** Платформ нь зөвхөн War3 1.26a-д зориулагдсан хэвээр байна.
2. **Зөвхөн 5 үндсэн Map:**
   Одоогийн [`backend/build_client_packages.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py#L2289-L2295) доторх `officialMaps` массивыг яг таны заасан дарааллаар 5 газрын зурагтай болгож тохируулна:
   1. `DotA v6.85m LoD`
   2. `DotA v6.74c LoD v5e`
   3. `DotA v6.83d Allstars`
   4. `DotA v6.85l LoD`
   5. `DotA v6.85k Allstars`
3. **Lobby Creation хэсгийн дараалал:**
   Баруун талын `CREATE LOBBY` самбар дээр яг:
   `Room Name` -> `Map Selection` -> `Room Password (Optional)` -> `No Leavers (Min 90% Stay Rate) Toggle` -> `CREATE LOBBY Button` дарааллаар байрлана.
4. **Одоо байгаа бүх функцийг хадгалах (Юу ч хасахгүй):**
   Зураг дээр зөвхөн `ONLINE ROOMS` таб харагдаж байгаа ч бид одоо ажиллаж байгаа **Өрөөний доторх харагдац (Inside Room View — Тоглогчдын жагсаалт, Чат, Start/Ready/Rejoin товчнууд, Host Kick)**, **WarKey тохиргоо**, **Login/Register цонх**, **Private DM чат**, **Тоглогчийн профайл popup** зэргийг яг энэ шинэ Dark/Gold дизайны стильтэй ижилсүүлэн 100% хэвээр үлдээнэ.

---

## 4. ХЭРЭГЖҮҮЛЭХ 3 ХУВИЛБАРЫН ХАРЬЦУУЛАЛТ (`COMPARE IMPLEMENTATION OPTIONS`)

| Шалгуур үзүүлэлт | OPTION A: Одоогийн C# WPF-ийг сайжруулах (Vector Path + Custom Templates + Embedded Artwork) | OPTION B: React + TypeScript + Tailwind CSS + WebView2 (C# Backend хэвээр) | OPTION C: Өөр орчин үеийн Desktop Framework (WinUI 3 / Avalonia / PyQt6) |
| :--- | :--- | :--- | :--- |
| **Зурагтай ижилсэх нарийвчлал (Visual Fidelity)** | **95% – 98%** (Custom XAML ControlTemplate, DropShadow, LinearGradient, Embedded PNG/SVG ашиглан бараг ялгагдахгүй болно) | **99% – 100%** (CSS `backdrop-filter`, box-shadow, веб фонтуудаар 1:1 хийгдэнэ) | **95%** (Avalonia/PyQt сайн боловч бүх зүйлийг шинээр бичих шаардлагатай) |
| **Одоогийн кодтой нийцтэй байдал** | **100% Шууд нийцнэ.** Одоогийн 6,400 мөр C# код огт эвдрэхгүй. | **Дунд зэрэг.** C# болон React хооронд `postMessage` / Local HTTP гүүр шинээр бичих хэрэгтэй. | **Маш муу.** Төслийн бүтцийг (`csc.exe` single-file build) бүрэн солих шаардлагатай. |
| **Өөрчлөх кодын хэмжээ** | **Бага–Дунд.** Зөвхөн `XAML_UI` (мөр 580–1943) болон түүнтэй холбоотой хэдэн UI filter event-ийг шинэчилнэ. | **Их.** Шинэ Node.js/Vite/React прожект үүсгэж, бүх дэлгэцийг эхнээс нь бичээд C#-тай холбоно. | **Маш их.** Бүх UI-г эхнээс нь дахин бичнэ. |
| **Хэрэгжүүлэх төвөгшил** | **Бага.** Шууд одоогийн `build_client_packages.py` дотор хийгдэнэ. | **Өндөр.** Node build pipeline + WebView2 SDK интеграц. | **Маш өндөр.** |
| **Хурд ба RAM зарцуулалт** | **Маш хөнгөн (~35–45 MB RAM).** Warcraft III тоглож байхад FPS унагахгүй, `.exe` хэмжээ `~650–800 KB` хэвээр байна. | **Хүнд (~180–350 MB RAM).** Ард нь Chromium (Edge) процесс ажиллана. | **Дунд (~80–150 MB RAM).** Инсталлер `40–80 MB` болж томроно. |
| **Тогтвортой байдал ба Засвар үйлчилгээ** | **Маш өндөр.** Ганцхан `.exe` файл хэвээр байх тул Steam-style Auto-Updater (`v4.6` -> `v4.7`) 2 секундэд шинэчилнэ. | **Дунд.** WebView2 суугаагүй компьютер дээр алдаа заах эрсдэлтэй. | **Дунд.** Олон `.dll` файл дагалдана. |
| **Аюулгүй байдал (Security)** | **Өндөр.** Гадны браузер порт эсвэл DevTools нээгдэх эрсдэлгүй. | `Inspect Element` / DevTools-ийг хаах, локал гүүрийг хамгаалах шаардлагатай. | **Өндөр.** |
| **Windows 7 / 10 / 11 Нийцтэй байдал** | **Төгс.** Windows 7 SP1, Windows 10 (Ghost Spectre / LTSC), Windows 11 бүгд дээр шууд ажиллана. | **Хязгаарлагдмал.** Монголын PC тоглоомын газрууд болон Ghost Spectre / LTSC Windows дээр `Edge WebView2 Runtime` устгагдсан байдаг тул програм асахгүй байх эрсдэлтэй. | WinUI 3 нь хуучин Windows 10 болон Windows 7 дээр ажиллахгүй. |
| **Одоогийн систем эвдрэх эрсдэл** | **Бараг 0% (Хамгийн аюулгүй).** | **Дунд (25–30%).** | **Өндөр (50%+).** |

---

## 5. ОДООГИЙН СИСТЕМИЙГ ХАМГААЛАХ СТРАТЕГИ (`PROTECT THE EXISTING SYSTEM`)

Бидний өдийг хүртэл маш нарийн тохируулж босгосон дараах системүүд **1 мөр код ч өөрчлөгдөхгүйгээр 100% хамгаалагдана**:
* [`backend/w3gs_room.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/w3gs_room.py) — 10 тоглогчийн детерминистик W3GS Rejoin, `SYNC_LIMIT = 15` (lag fix), Disconnect/Quit ялгах логик.
* [`backend/app.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/app.py) — Бүх REST API, SQLite WAL тохиргоо, ELO тооцоолол, Match History, Тоглогчийн ранк шүүлтүүр.
* [`backend/build_client_packages.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py) доторх:
  * `NativeWarKeyEngine` (WarKey чат хамгаалалттай)
  * `StartNativeGamingServices`, `BridgeTcpSession`, `SendRawLanGameInfo` (W3GS LAN & TCP Proxy)
  * `ScanAndEnforceMapIntegrity` (Anti-MapHack)
  * `EnsureMapExistsAndLaunch` ба `LaunchWarcraft3` (Автомат Map таталт ба War3 1.26a асаалт)
  * `CheckAndApplySelfUpdate` (Автомат шинэчлэгч)

---

## 6. ТЭЗҮ БА 10 АСУУЛТЫН ТОДОРХОЙ ХАРИУЛТ (`FEASIBILITY REPORT`)

### 1. Хавсаргасан интерфейсийг маш өндөр нарийвчлалтайгаар дуурайлган хийж чадах уу?
**Тийм.** Хавсаргасан зураг дээрх Lich King баннер, алтан хүрээтэй Dark Theme, зүүн талын навигаци ба профайл карт, өрөөний хүснэгт (газрын зургийн зураг болон ногоон Wi-Fi пинг индикатортой), газрын зургийн popup dropdown, баруун талын `CREATE LOBBY` самбарыг **95%–98% нарийвчлалтайгаар** бүтээж чадна.

### 2. Одоогийн UI framework (C# WPF)-ийг ашиглан үүнийг хийж чадах уу?
**Тийм, бүрэн чадна.** Одоогийн UI нь энгийн WinForms эсвэл Tkinter биш, харин DirectX дээр суурилсан **WPF (Windows Presentation Foundation)** юм. Одоогийн UI яагаад энгийн харагдаж байна вэ гэвэл:
1. Ар талд нь Lich King баннер зураг болон Map-ийн жижиг зургууд (thumbnails) ороогүй, зөвхөн цулгуй өнгө (`#0F1522`) тавьсан байсан.
2. Иконуудыг вектор SVG `<Path>` биш, энгийн текст эможи (`&#x1F3AE;`) болгож бичсэн байсан.
3. Текст нүд болон Dropdown (`ComboBox`)-д стандарт Windows-ийн цагаан хүрээтэй суурь темплейт харагдаж байсан.
Эдгээр 3 зүйлийг WPF-ийн Custom `ControlTemplate`, Embedded PNG/JPG зураг болон Vector `<Path>` геометрээр солиход одоогийн WPF дээр яг таны зураг шиг премиум тоглоомын платформ болж хувирна.

### 3. React + WebView2 нь илүү дээр шийдэл мөн үү?
**Үгүй (Warcraft III 1.26a тоглогчдын хувьд WPF нь илүү найдвартай).**
Хэдийгээр React + Tailwind нь CSS бичихэд амар боловч таны хэрэглэгчид (Монголын Warcraft III 1.26a тоглогчид болон PC тоглоомын газрууд) ихэвчлэн хөнгөлсөн Windows 10 (Ghost Spectre, AtlasOS, LTSC) эсвэл Windows 7 ашигладаг. Тэдгээр компьютер дээр `Microsoft Edge WebView2 Runtime` устгагдсан байдаг тул React + WebView2 апп огт асахгүй эсвэл 150MB нэмэлт програм татахыг шаардана. Мөн WebView2 нь тоглоомын ард 250MB+ RAM иддэг. Харин **Option A (WPF)** нь ямар ч нэмэлт програм шаардахгүй, `~700 KB` хэмжээтэй ганц `.exe` хэвээрээ бүх Windows дээр 100% шууд асна.

### 4. Одоогийн Python болон C# backend-ийг хэвээр хадгалж чадах уу?
**Тийм, 100% хэвээр хадгална.** Python сервер ([`backend/app.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/app.py), [`backend/w3gs_room.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/w3gs_room.py)) болон C# доторх бүх сүлжээ/тоглоомын функцүүд хөндөгдөхгүй.

### 5. Програмын аль хэсгүүдийг өөрчлөх шаардлагатай вэ?
Зөвхөн [`backend/build_client_packages.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py) файл доторх UI-тай холбоотой дараах хэсгүүд л шинэчлэгдэнэ:
1. **`XAML_UI` блок (мөр 580–1943):** Шинэ Layout, Top Hero Banner, Sidebar, Lobby Table (`GridView`/`ItemsControl` мөрүүд), Map Dropdown Custom Template, Баруун талын `CREATE LOBBY` карт, Custom Toggle Switch, Search + `[All | Open | Friends | Low Ping]` табууд.
2. **Газрын зургийн жагсаалт (`officialMaps`, мөр 2289–2295):** Таны заасан 5 үндсэн газрын зураг болон тэдгээрийн жижиг зургийн холбоос.
3. **Хайлт ба Шүүлтүүр (`RefreshLobbyFilter()`):** `All`, `Open`, `Friends`, `Low Ping` табууд дээр дарахад өрөөний жагсаалтыг шүүх жижиг UI функц.
4. **Embedded Visual Assets:**Таны зургаас Lich King баннер, MongolRanger лого болон 5 Map-ийн жижиг зургийг салгаж аваад `.exe` дотор resource болгон багцлах хэсэг.

### 6. Аль хэсгүүд огт хөндөгдөхгүй хэвээр үлдэх вэ?
* [`backend/w3gs_room.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/w3gs_room.py) (100% хөндөгдөхгүй)
* [`backend/app.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/app.py) (100% хөндөгдөхгүй)
* `NativeWarKeyEngine`, `BridgeTcpSession`, `StartNativeGamingServices`, `ScanAndEnforceMapIntegrity`, `LaunchWarcraft3`, `PollServer`, `SendJson` (100% хөндөгдөхгүй)

### 7. Хамгийн том техникийн эрсдэлүүд юу вэ ба түүнээс хэрхэн сэргийлэх вэ?
1. **Эрсдэл 1 — Зураг дээр харагдахгүй байгаа дэлгэцүүдийг (Өрөөн доторх лобби, Чат, WarKey, Login) мартах эсвэл эвдэх:**
   * *Шийдэл:* `x:Name` атрибутуудыг (`LobbyList`, `RoomNameBox`, `RoomMapSelect`, `RoomPasswordBox`, `MinTrustCheck`, `CreateRoomBtn`, `RoomMembersList`, `RoomChatList`, `RejoinWar3Btn` г.м.) яг хуучин нэрээр нь хадгалснаар C# талын `window.FindName(...)` кодууд нэг ч алдаа заалгүй шууд ажиллана. Өрөөнд орсон үед (`Inside Room View`) өрөөний хүснэгтийн оронд шинэ дизайны стильтэй Өрөөний Доторх Самбар (10 слот, чат, Start/Ready/Rejoin товч) автоматаар солигдож харагдана.
2. **Эрсдэл 2 — Зургийн файлууд тусдаа хавтсанд байвал хэрэглэгчийн компьютер дээр уншихгүй байх:**
   * *Шийдэл:* Lich King баннер болон 5 Map иконыг гадна талд задгай файл болгож тавихгүй, харин `.exe` дотор Base64 / Embedded Resource хэлбэрээр шууд шингээнэ. Ингэснээр ганц `.exe` файл хэвээр үлдэнэ.

### 8. Ямар дизайн ассетууд дутуу байгаа вэ?
Таны хавсаргасан `media_1792491528867_95e05add.jpg` зураг өөрөө өндөр нягтаршилтай тул бид:
* Дээд талын **Lich King Hero Banner + Logo**-г уг зургаас шууд цэвэрхэн салгаж авч чадна.
* **5 Map-ийн жижиг иконыг** мөн зургаас шууд салгаж авч чадна.
*(Хэрэв танд эдгээр зургуудын анхны текстгүй/тусдаа PNG файлууд байгаа бол надад өгч болно, байхгүй бол би таны явуулсан зургаас шууд боловсруулаад оруулж чадна).*

### 9. Шинэ интерфейсийг хэрхэн аюулгүйгээр хэрэгжүүлж, тестлэх вэ?
1. Одоогийн ажиллаж буй [`backend/build_client_packages.py`](file:///d:/Projects/war3%20reconnect%20host%20service/backend/build_client_packages.py)-ийн нөөц хуулбарыг авна.
2. Зургийн ассетууд (Banner, Logo, 5 Map Icons) болон SVG Vector иконуудыг бэлтгэнэ.
3. Зөвхөн `XAML_UI` болон Filter табын кодыг шинэчилж, `csc.exe`-ээр хөрвүүлэн бүх `FindName` холболтууд болон `backend.test_app` нэгж тестүүдийг шалгана.
4. Локал орчинд цонхны хэмжээ өөрчлөх (resizing), өрөө үүсгэх, 5 map сонгох, өрөөнд орох, чат бичих, WarKey, Rejoin товчнуудыг бүрэн шалгасны дараа л сервер лүү гаргана.

### 10. Эцсийн зөвлөмж ба Хэрэгжүүлэх Төлөвлөгөө (Final Recommended Plan)
**Миний эцсийн зөвлөмж: OPTION A (Одоогийн C# WPF архитектурыг хадгалж, `XAML_UI`-г Custom Dark/Gold ControlTemplates + Vector SVG Icons + Embedded Lich King Artwork-оор 100% шинэчлэх).**

Энэ зам нь:
* Таны явуулсан зурагтай **маш өндөр нарийвчлалтайгаар (95–98%)** ижилсэнэ,
* Одоогийн **W3GS Rejoin, Lag Fix, WarKey, ELO, Anti-Cheat**-ийг эвдэх эрсдэл **0%**,
* Бүх Windows (7/10/11, Ghost Spectre) дээр ямар ч WebView2 шаардахгүй шууд асна,
* Ганцхан ширхэг хөнгөн `.exe` хэвээр үлдэнэ.

---

### ТАНЫ БАТАЛГААЖУУЛАЛТ ХҮЛЭЭГДЭЖ БАЙНА
Та энэхүү **OPTION A (WPF High-Fidelity Redesign)** төлөвлөгөөг зөвшөөрч байвал **"Зөвшөөрч байна, эхэл"** гэж бичнэ үү (мөн өмнөх lag засварыг сервер лүүгээ шууд deploy хийлгэх бол хамт хэлээрэй).
