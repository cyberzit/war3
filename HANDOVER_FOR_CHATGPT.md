# MongolRanger — Project Status & Handover Documentation
**Төслийн нэр:** MongolRanger (Warcraft III TFT 1.26a • DotA LoD Platform)  
**Хөгжүүлэлтийн огноо:** 2026-10-15  
**Зорилго:** GameRanger шиг монгол хэрэглэгчдэд зориулсан онлайн лобби, хэрэглэгчийн бүртгэл, сааталгүй (zero-latency) WarKey (Inventory + Skill), автомат тасралтгүй сервертэй платформ.

---

## 1. Төслийн ерөнхий дүрэм ба шаардлагууд (Strict Constraints)
1. **Зөвхөн бие даасан `.exe` файл байна:**
   - Хэрэглэгч ямар ч `.bat` файл, консол цонх ашиглахгүй.
   - Үндсэн ажиллах файл: `MongolRanger.exe` (PyInstaller 1-file compilation).
2. **WarKey-ийн дизайн ба зарчим:**
   - Анх нээхэд бүх нүд хоосон (`—`) байна. Ямар ч анхдагч үсэг/тоо урьдчилан тавигдаагүй байна.
   - Зөвхөн хэрэглэгчийн гараараа тохируулсан хамгийн сүүлийн товчлуурууд хадгалагдаж ажиллана.
   - Backspace эсвэл хулганы баруун товч дарахад тухайн нүд арилж хоосон (`—`) болно.
   - Хэрэггүй товчлуур байхгүй (Invoker, нэмэлт тохиргоо, асаах/унтраах товч, learn skill гэх мэт илүү дутуу зүйлс байхгүй).
3. **Гар (Keyboard)-ын тусгаарлалт (Strict OS Isolation):**
   - WarKey нь зөвхөн дэлгэц дээр Warcraft III идэвхтэй байх үед л ажиллана.
   - Windows, вэб хөтөч, чат, Word зэрэг дээр гар 100% чөлөөтэй ажиллана, ямар ч нөлөө үзүүлэхгүй.
   - Тоглоом дотор `Enter` дарж чат бичих үед товчлуурууд скилл/эд зүйл дарахгүй, чат бичигдэнэ.
   - `Alt + Tab`, `Windows товч` дарахад чөлөөтэй гарна.

---

## 2. Файлын бүтэц (Codebase Architecture)
```
d:\Projects\war3 reconnect host service\
│
├── MongolRanger.exe          # Бэлэн болсон хэрэглэгчийн үндсэн биелэгдэх файл (11.18 MB)
├── mongolranger.py           # Үндсэн GUI код (Login, Lobby, WarKey Grid, Settings, Auto-Patcher)
│
├── core/
│   ├── __init__.py
│   ├── warkey.py             # Aegis WarKey Win32 Low-Level Hook Engine (WH_KEYBOARD_LL)
│   └── config.py             # Warcraft III хавтас автоматаар илрүүлэх, тохиргоо хадгалах
│
├── data/
│   ├── users.json            # Орон нутгийн туршилтын хэрэглэгчдийн бааз (Нууц үг hash-тай)
│   └── settings.json         # Хэрэглэгчийн хадгалсан товчлуурын тохиргоо (Inventory + Skills)
│
└── dist/
    └── MongolRanger.exe      # PyInstaller-ийн build output
```

---

## 3. Олсон бүх алдаанууд ба шийдлүүд (Bugs Found & Resolutions)

### Алдаа 1: Систем даяар Keyboard ямар ч үйлдэл хийх эрхгүй гацсан
* **Шинж тэмдэг:** `MongolRanger.exe` ажиллах үед компьютерын гар ямар ч програм дээр үсэг бичихээ больж систем даяар гацсан.
* **Шалтгаан:** 64-bit Windows дээр `WH_KEYBOARD_LL` hook-ийн буцах утга (LRESULT) нь 64-bit (`ctypes.c_ssize_t`) байх ёстой атал кодонд 32-bit `ctypes.c_long` гэж тодорхойлсон байсан. Ингэснээр RAX регистрийн дээд 32 битэд санамсаргүй тоо үлдэж, Windows үйлдлийн систем бүх товч даралтыг "Блоклох/дарж устгах" (Non-zero return value) гэж үзсэн.
* **Шийдэл:** `core/warkey.py` дотор `HOOKPROC`-ийг 64-bit цэвэр LRESULT болгосон:
  ```python
  HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
  user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
  user32.CallNextHookEx.restype = ctypes.c_ssize_t
  ```

### Алдаа 2: Warcraft III-аас гадуур товчлууруудыг дарж саад учруулсан
* **Шалтгаан:** Hook функц дотор идэвхтэй цонхыг шалгадаггүй байсан.
* **Шийдэл:** Callback-ийн хамгийн эхэнд `is_war3_foreground()` шалгуурыг хийсэн. Хэрэв дэлгэц дээр Warcraft III цонх биш бол 1 миллисекундын дотор `CallNextHookEx` дуудаж буцаана:
  ```python
  def is_war3_foreground() -> bool:
      hwnd = user32.GetForegroundWindow()
      if not hwnd: return False
      cls_buf = ctypes.create_unicode_buffer(64)
      user32.GetClassNameW(hwnd, cls_buf, 64)
      return cls_buf.value == "Warcraft III"
  ```

### Алдаа 3: Warcraft III дотор Inventory товчнууд дарагдахгүй байсан (`KEYEVENTF_EXTENDEDKEY` алдаа)
* **Шалтгаан:** Numpad 7, 8, 4, 5, 1, 2 товчийг дуурайлгаж дарахдаа `flags |= KEYEVENTF_EXTENDEDKEY` гэж тавьсан байсан. Компьютерын гарны архитектурт Numpad тоон товчнууд нь "Extended" БИШ байдаг. Extended болгосноор scancode `0x47` нь Numpad 7 биш харин `Home` товч, `0x48` нь `Up Arrow`, `0x4F` нь `End` товч болж хувирч байсан.
* **Шийдэл:** `KEYEVENTF_EXTENDEDKEY`-ийг бүрэн хасаж, Virtual Key (`wVk`) болон Scancode (`wScan`)-ийг зэрэг `SendInput`-ээр явуулсан:
  ```python
  def send_hardware_scancode(vk_code: int, key_up: bool = False):
      scan = user32.MapVirtualKeyW(vk_code, 0)
      flags = (KEYEVENTF_KEYUP if key_up else 0)
      inp = INPUT(
          type=INPUT_KEYBOARD,
          ki=KEYBDINPUT(wVk=vk_code, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=AEGIS_EXTRA_INFO),
      )
      user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
  ```

### Алдаа 4: Тоглоом дотор чат бичихэд товчлуур скилл/эд зүйл дарж зөрсөн
* **Шийдэл:** Ухаалаг чат горим (Smart Chat):
  - `Enter` дарах үед `self.chat_active` төлөв сэлгэгдэнэ.
  - Чат идэвхтэй үед ямар ч үсэг тоог WarKey барихгүй, шууд тоглоомын чат руу чөлөөтэй бичнэ.
  - Мессежээ явуулаад `Enter` дарах, эсвэл `Esc` дарахад чат горим шууд хаагдаж WarKey идэвхжнэ.
  - Хэрэв тоглогч тоглоомоос өөр цонх руу шилжвэл `self.chat_active = False` болж автоматаар шинэчлэгдэнэ.

### Алдаа 5: Backspace дарахад товч арилахгүй, "Backspace" гэж оноогдсон
* **Шалтгаан:** Түлхүүр барих үед Backspace (VK 0x08)-ийг энгийн товчлуур шиг бүртгэж байсан.
* **Шийдэл:** `_on_key_captured` дотор `vk in (0x08, 0x2E)` (Backspace / Delete) ирвэл шууд `self._clear_slot(slot_type, idx)` дуудаж нүдийг хоосон (`—`) болгож цэвэрлэдэг болгосон.

---

## 4. Серверийн мэдээлэл (Production Server Access)
Хэрэглэгчийн одоогийн вебсайт ажиллаж буй хүчирхэг серверийн холболт:
* **Host / IP:** `37.27.115.231` (Hetzner Dedicated Server)
* **Port:** `22` (SSH)
* **User:** `root`
* **SSH Key зам:** `C:\Users\my tech\.ssh\id_ed25519_kora`
* **Серверийн үзүүлэлт:** Ubuntu 24.04 LTS (Noble), 64-bit AMD64, **128 GB RAM** (124Gi total, 118Gi free), ачаалал маш бага.
* **SSH холбогдох комманд:**
  ```powershell
  ssh -i "C:\Users\my tech\.ssh\id_ed25519_kora" root@37.27.115.231
  ```
* ⚠️ **МАШ ЧУХАЛ ДҮРЭМ:**
  Сервер дээр одоогийн вебсайт (Nginx, Node, Web app гэх мэт) ажиллаж байгаа тул **одоо ажиллаж буй портал, өгөгдлийг огт хөндөж болохгүй!**
  MongolRanger-ийн серверийг `/opt/mongolranger/` гэсэн тусдаа хавтас үүсгэж, тусдаа порт (жишээ нь `5050` эсвэл `8050`) дээр systemd service эсвэл docker-оор ажиллуулах ёстой.

---

## 5. Дараагийн хийх ажлууд (Next Steps for ChatGPT Astra)

1. **Сервер талын Backend байгуулах (Remote API & WebSocket):**
   - Сервер дээр `/opt/mongolranger` хавтас бэлтгэх.
   - Python FastAPI эсвэл Node.js дээр Хэрэглэгчийн бааз (Auth/Register), Өрөө үүсгэх (Rooms), Чат үйлчилгээг порт `5050` дээр асаах.
   - Сервер талын өгөгдлийг SQLite эсвэл PostgreSQL дээр хадгалах.
2. **Client `mongolranger.py`-ийг сервертэй холбох:**
   - Орон нутгийн `data/users.json` биш, серверийн `http://37.27.115.231:5050/api` руу хүсэлт илгээж нэвтэрдэг / бүртгүүлдэг болгох.
   - Өрөөнд орж тоглоход тоглогчдын хоорондын мэдээлэл серверийн WebSocket-ээр дамжина.
3. **Warcraft III Reconnect & Dedicated Host Bot (GHost++):**
   - Сервер дээр Warcraft III 1.26a болон DotA LoD газрын зургийг байршуулж, тасралтгүй ажиллах GHost++ ботыг тохируулах.
   - MongolRanger өрөөнөөс "Start Game" хийхэд серверийн бот тоглоомыг автоматаар үүсгэж, тоглогч холболт тасарсан ч 1 минутын дотор дахин холбогдох (reconnect) боломжийг олгох.
4. **Хөрвүүлэлт хийх (PyInstaller):**
   - `mongolranger.py` кодонд өөрчлөлт хийсний дараа үргэлж дараах коммандаар `.exe` болгож шинэчилнэ:
     ```powershell
     pyinstaller --noconsole --onefile --clean --name MongolRanger mongolranger.py
     Copy-Item -Path "dist\MongolRanger.exe" -Destination "MongolRanger.exe" -Force
     ```

## 2026-10-15 — ChatGPT WarKey verification update

Current scope: remove Ctrl+F5; verify automatic foreground/chat handling before continuing lobby/network/reconnect work. Installer remains deferred.

Implemented:
- Removed Ctrl+F5 toggle; configured mappings remain enabled while client runs.
- Correct native INPUT union and pointer-sized extra-info fields on 64-bit Windows.
- Foreground identification checks Warcraft III window class and war3.exe process. Process access denial is reported and original keys pass through.
- Enter autorepeat protection, Ctrl+Enter tracking, chat-state retention across focus changes, held-key release and original target retention across mapping changes.
- Tab remains a supported user mapping. Ctrl/Alt/system chords pass through.
- WarKey UI reports hook/error status instead of an unconditional working label.
- Updated obsolete default-mapping expectations in tests/test_aegis_suite.py.

Validation:
- tests/test_warkey_regression.py: 16 tests passed. Win32 event injection is mocked in these tests; this does not prove actual game input delivery.
- Python compile checks passed; PyInstaller build succeeded. Root and dist MongolRanger.exe SHA256: 41F2817918B12D524CDB61B919CFFA8383D5A4625C2D044DC3F3862E805DD2BB.
- Opened original DotA LoD 6.85m.w3x in local single-player. Chat accepted physical U/Y inputs, but remapping was NOT active: OpenProcess(QUERY_LIMITED_INFORMATION) returned Access denied (5) for war3.exe. Therefore neither chat suppression nor item/skill remapping is considered game-verified.
- Observed updated GUI displaying the process-access error correctly after a game key press.
- Temporary manual test used isolated settings with U -> Num7, Y -> Q. Existing data/settings.json was preserved. Test client closed; local Warcraft test remains open.

Next required step:
User opens root MongolRanger.exe with Run as administrator and logs in if prompted. Agent then tests real item/skill activation, chat submit/cancel, Ctrl+Enter, focus switching and Ctrl+F5. Windows security/authentication prompts must be handled by user.
Known limitation: chat state is tracked by Enter/Escape, not read from actual game UI. Menus, lobby text and a chat already open before startup still require validation; do not claim full chat detection or finished WarKey yet.
Only after WarKey acceptance continue shared lobby/auth/network work; crash reconnect has not been proven by this change.

## 2026-10-16 — WarKey live game verification

Supersedes yesterday's administrator-rights diagnosis. The existing client still reported process access denied when launched as administrator. That failure was from opening a Warcraft process handle; it did not establish that input injection required elevation.

Changed core/warkey.py to identify the foreground window's PID through a Toolhelp process snapshot (exact war3.exe name plus Warcraft III window class), with a short identity cache. No process handle, memory access, privilege change or game patch is needed. Snapshot failure remains fail-open for keyboard input. Successful remapping clears the previous error.

Validation:
- 19 regression tests passed, including actual current-process identification without OpenProcess, invalid snapshot handling and rejecting a non-game process with the Warcraft window class.
- Original DotA LoD 6.85m, local single-player, actual Warcraft III 1.26a window. Non-elevated Python client using the same MongolRangerApp and core/warkey.py, isolated temporary settings: U -> Num7, Y -> D.
- Y cast learned Death Pulse: mana dropped from 299 to 195, then cooldown appeared. With chat open Y typed literal y without casting. After Enter submission Y cast again (mana 174, cooldown 8.0).
- U activated first-slot Kelen's Dagger; clicking the ground teleported the hero and started item cooldown.
- Ctrl+F5 no longer disabled remapping. Ctrl+Enter opened chat; U typed literal u. Switched to client and typed literal uy into an unsent input field, then returned to game: chat remained open; Y appended y, giving uy without casting. Escape closed chat and U immediately re-entered Blink targeting.
- No WarKey error displayed during these non-elevated tests.
- Original data/settings.json preserved (Q/Space/Tab/4 inventory, R/Z/W/E skills). Test mappings were only in a temporary directory.
- Rebuilt root and dist MongolRanger.exe, matching SHA256 DCCC298CDE1BA88BE383F7CD4C7BFE983644C4F38021AE5C5401E41B3F0B1537. Live remapping was validated through the source GUI harness; packaged executable authentication is not automated.

Coverage limits: actual tests covered these two configured slots in one local LoD match; not every inventory slot, hero, multiplayer chat mode or menu/startup state. Enter/Escape tracking is still heuristic; menus and already-open chat at engine startup need a later targeted pass. Do not call reconnect or network play verified.

Work order: core WarKey gameplay checks now passed; next inspect and implement real lobby/auth/room communication, then host/client transport reliability, then two-player crash-reconnect proof. Installer stays last.

Packaged executable follow-up: launched the rebuilt root MongolRanger.exe normally. It opened the saved ZEV session without any authentication interaction. With the original user mappings, Q -> Num7 activated Blink targeting and Z -> D cast Death Pulse (mana 299 -> 192, cooldown 7.1). Thus packaged item/skill delivery was also verified. Temporary harness closed; rebuilt client remains running, local game left paused at F10 menu.

## 2026-10-16 — Isolated production lobby API deployed

User authorized co-location on kora.mn host, explicitly requiring no changes/damage to kora.mn, then requested more RAM/performance. Deployed mongolranger.service on 37.27.115.231:8050 with dedicated TLS/private CA, /opt/mongolranger code/venv, /var/lib/mongolranger SQLite and unprivileged mongolranger account. Final limits: 2 GiB RAM maximum, 1 GiB high watermark, CPUQuota 200% (two of 32 logical CPUs), TasksMax 128, concurrency 128. Initial 256 MB / 25% proposal was superseded before startup.

Implemented backend/app.py: salted scrypt credentials, hashed/expiring bearer sessions, authenticated room create/list/join/leave, host-only heartbeat, bounded member chat, expiry and rate/body limits. Tests in backend/test_app.py passed locally and remotely (6 groups). External TLS two-account lifecycle smoke passed; synthetic accounts cleaned up. Service restart passed; boot enablement confirmed.

Isolation evidence: 36 existing website/config root file hashes identical before/after; Caddy, both Next servers and PostgreSQL listener PIDs unchanged; kora.mn HTTP 200 throughout spot checks. No Caddy/DNS/firewall/global package/website DB changes. Effective service namespace denies read access to both website package files and /etc/caddy/Caddyfile. Service observed ~34 MiB RAM. Small health benchmark: server-local p50 9.58ms at 5 concurrent requests; workstation persistent TLS p50 256.6ms. Network latency is not addressed by more RAM.

See deploy/OPERATIONS.txt for endpoints, paths, resource limits, TLS renewal (leaf expires 2027-10-16), and service-only rollback. backend/server-ca.crt is PUBLIC CA trust material fetched over trusted SSH; private keys stay on server. Future native client must bundle/trust this CA specifically with hostname verification, never disable TLS checks. No global CA install and no kora.mn TLS key reuse.

Remaining: connect desktop UI to this API (not done this turn), persistent HTTP connections, then host-PC game networking and independent crash-reconnect proof. Current lobby API uses HTTP polling; no WebSocket or game relay yet. Installer remains last.

## 2026-10-16 — Save-based single-player rejoin requirement and source audit

User explicitly selects existing autosaves as the recovery foundation. User reports Gemini verified that disconnect autosaves retain heroes, levels, gold and items. Preserve this reported result; it is not evidence that a restarted client has joined an unchanged live session. Do not substitute replay-from-match-start or mandatory reload of all players. Engine/map/host modifications are authorized. Installer remains deferred.

Read-only source findings this turn:
- ghost/game_base.cpp:1423-1435 queues save action 0x06 under the departing PID and sends actions BEFORE PLAYERLEAVE_OTHERS at line 1460. The remaining Warcraft processes produce the save; the host bot requests it. The current path then commits the departure, which is incompatible with reserving the same active participant for recovery.
- core/recovery_manager.py host_recovered_match starts with self.stop(), then loadsg/hostsg creates a replacement saved-game lobby. This must not be wired to the requested live-session Rejoin button.
- core/save_sync.py serves the most recent file by timestamp, without binding it to a match/checkpoint or proving it is finished. Existing transfers are a local prototype, not the deployed authenticated central-server save service.
- tools/map_converter.py contains save-menu, allocator, save counter and serialization patches. These are useful save foundations; its introductory comments are not proof of live session reattachment.
- Actual local test.w3z and test2.w3z exist (2026-10-15). ghost.log records parsing test2 and creating [Restore] test10, then a player joining its lobby. The inspected segment does not establish two-client continuation or a ten-player crash recovery result.

Next experimental boundary, before product UI integration:
1. Preserve the original host session and player PID on disconnect; defer the permanent leave event and reserve the seat until explicit drop/expiry.
2. Establish a synchronized save boundary on surviving clients, including pending actions and save-completion acknowledgement. Freeze simulation at that boundary while maintaining transport. Merely stopping action packets may trigger game timeouts; heartbeat/lag handling must be tested.
3. Capture one complete save, map/build identity, participant/PID layout and checkpoint identity. Upload/download atomically with hash verification, scoped to authenticated match members. Never select another match's latest file.
4. Prototype an isolated saved-game loading handshake for the returning Warcraft process, then attach its original participant identity and align transport/simulation counters with the waiting session. This is a research hypothesis, not an implemented or proven bridge. Keep healthy clients in their original game. Do not bypass state/checksum mismatches to simulate success.
5. First acceptance test: two real clients, kill one Warcraft process, restore that one from the checkpoint, issue commands on both and verify synchronized hero/item/gold/cooldown/world state. Then repeat crashes, host-player crash and ten-player tests. Account for a host PC loss separately from its Warcraft process crashing.

No engine patch, executable rebuild, remote deployment or live recovery test was performed in this audit. The unresolved implementation is checkpoint-to-live-session reattachment, not whether saves are useful.

## 2026-10-16 — Two-client baseline and extended waiting requirement

Subsequent live experiment supersedes the preceding audit's no-live-test statement:
- Two isolated Warcraft copies in runtime/two-client-lab/A and B joined Autosave Lab on this computer. Instance event names and LAN UDP ports were separated. Installed game files were not modified by this experiment.
- The user forcibly ended test player ZEVB's Warcraft (PID 22652). GHost observed disconnect at 10:51:56; the surviving client produced GHost++ AutoSave Autosave Lab (ZEVB).w3z at 10:51:57, 4,731,884 bytes, SHA256 8084da2ebf0a0889447c892750e39de1a5b1edb9d451640eb4b14130db088fdd.
- The checkpoint inspector decompressed all 1320 blocks and found both occupied player slots. This does not validate restored world state or live rejoin.
- Baseline GHost sent the permanent leave event and ended the one-player game after 60 seconds. Neither seat reservation nor a recovery pause is implemented.
- Fresh B (PID 12312) saw Checkpoint Load Probe but joining showed 'Unable to join the specified game'. No successful restoration or live rejoin was demonstrated. Investigate local save recognition and saved-game handshake before claiming recovery works.

Latest user requirement: router restarts and complete player-PC power cycles must have an extendable reconnect wait, with Add time. A short fixed timeout is insufficient. The following are proposed product defaults, not implemented behavior:
- Default initial wait 3 minutes, configurable by host before a match; Add time extends the existing deadline by 2 minutes per accepted request. Repeated extensions must be possible while participants wish to wait; expiry must not silently destroy the checkpoint.
- Connected players can request more time; the host approves extensions and alone can explicitly drop a player while present. Requests need authenticated match membership, deduplication and server-authoritative deadlines; reconnecting/restarting the client must not reset the countdown.
- If the host PLAYER is disconnected but the host process is alive, retain the host role and allow remaining connected participants to approve extra time by majority. Other players do not acquire a manual Drop button. A race between rejoin, expiry and extension must have one authoritative outcome.
- If the host COMPUTER loses power, its local game server also stops. Add time alone cannot preserve that running session. Keep central checkpoint/metadata and treat this as whole-host recovery, a separate unproven path; do not promise unaffected live continuation.
- Automatic deadline expiry should move recovery to an explicit expired decision state, not delete saves. Exact continuation/drop behavior still needs engine testing, especially when the absent player is host. Keep checkpoint retention separate from wait timeout.
- Acceptance tests must include client restart, router-length outage, repeated Add time, duplicate/retried requests, simultaneous expiry/rejoin, host-player crash, and host-PC outage. Add time UI, authoritative timer and engine integration remain unimplemented.

## 2026-10-16 saved-game recognition and control investigation
- Exact baseline autosave bytes become discoverable/joinable when renamed checkpoint.w3z; original long GHost filename was not recognized by B. Exact filename restriction not isolated.
- Added recovery_lab/checkpoint_store.py and three tests: complete validated bytes staged under short content-addressed filenames, atomic publication, collision preservation. Eight checkpoint-related tests passed. Not integrated into production recovery flow.
- Both clients loaded Checkpoint Short successfully, preserving B/ZEVB Axe, level and resources. This was a NEW saved-game session with BOTH clients loading, not live single-client rejoin.
- Own hero visibility/control is faulty after sharing A's save with B. A had no hero; B had Axe. Level increases in earlier session do NOT establish controllability.
- Paired native saves pairchecku.w3z differ in first-block local slot/colour integers at offsets 0x11b/0x11f (A 0/1, B 5/7). tools/probe_checkpoint_perspective.py patches those two fields and rebuilds valid CRCs in B perspective.w3z; A uses original bytes. This experiment DID NOT fix B visibility. Do not ship as a fix.
- Current Perspective Probe clients A PID2216 window461158 and B PID24640 window395596; host PID5792, loopback6200/admin6201. Both loaded at 11:19:41. Controller session21209 retains launch handles; runtime/two-client-lab/force-crash-B-24640.request requests exact-child kill. Not exercised yet. Discovery relay session72143 may expire around11:26.
- Latest user correctly questions hero control. B right-click ground and minimap move to central lane did not produce expected visible displacement; double-click portrait recentered to same dark base. Explicit Move icon + ground target displays green order arrows, but successful movement still unproven. Need verify ownership/command execution and per-client visibility, not assume fog alone. No fresh crash/rejoin success demonstrated.
- Relevant new tools: tools/run_owned_lab_clients.py, tools/probe_checkpoint_perspective.py; modified tools/probe_saved_client_load.py stages short identical files and uses admin_name ZEV. Do not relaunch duplicate clients or overwrite live DLLs.

## 2026-10-16 11:39 local control comparison (latest)
- User asked fix hero visibility/control and whether running two Warcraft instances causes the defect.
- Ended only isolated Perspective Probe via admin !end 1. Created Fresh Control Probe, same two processes A2216/B24640. Both loaded in ~3s. Slot A ZEV=0/colour1, B ZEVB=5/colour7 (PID A3/B2 in this match, reversed versus old baseline).
- All Random selected (user interaction); A Techies and B Silencer. Explicit right-click tests visibly moved A from roughly(704,325) toward(931,259), B from(700,300) to(494,408). Both had correct vision. Two instances alone do not reproduce the visibility fault.
- Saved freshpair.w3z on BOTH clients at11:31:19. A SHA25638955d1c0b4b0906ecc2d9eaf81a4ebb304084c95e17a122d5f7eed4d0dbf228 (4628110bytes), B SHA2563a9ae6cf760f514f7994c74f947f9902b6affe5d918a325e1ed2bc8f36a560ad (4628537bytes). Both complete, same map/magic1631226096/seed99093636/slots; different local state.
- Successfully force-killed owned B24640 via controller marker at11:31:41. A generated GHost++ AutoSave Fresh Control Probe (ZEVB).w3z (4696766bytes). This new crash autosave has NOT been successfully rejoined.
- Force-killed A2216 after save captured; old controller exited. Launched new clients with tools/run_owned_lab_clients.py: A16984/window1443266, B21232/window526702, controller session72758. Native sky variables wa/wb now refer to these.
- Fresh Control Probe replay: GHost++ 2026-10-16 11-32 Fresh Control Probe (02m04s).w3g. Created Own Save Control using exact replay, !loadsg freshpair, admin_name ZEV. Each client retained ITS OWN freshpair bytes (no copy/header patch).
- Both loaded Own Save Control at11:35:42 (A3.08s,B5.00s). B Silencer visible with own base vision; explicit move from(480,400) to(721,302) completed, confirmed next screenshot. A Techies visible and explicit move from(920,260) to(724,335) completed, confirmed at11:39. This proves a fresh-process two-client OWN-SAVE reload with hero movement, NOT live rejoin from survivor autosave. No items/spells acceptance yet. No engine binary fix this turn.
- Stronger evidence points to sharing another client's serialized local state. Exact root field(s) remain unknown. Header-only slot/colour patch did not fix it. Own-save success does not solve obtaining absent player's current perspective after crash; cannot substitute older own save without tick mismatch.
- tools/probe_saved_client_load.py no longer blindly copies A save to B: requires explicit short --checkpoint filename and exact --replay; rejects missing B file, differing map/match/slots/seed/magic, wrong pinned local slot/colour. These checks do NOT prove same tick. Real wrong-perspective regression using checkpoint.w3z rejected before host/process mutation. Python compile passed, 8 checkpoint tests passed. Legacy core/save_sync and core/recovery_manager still not fixed/integrated; do not claim production recovery works.
- Added tools/relay_lab_discovery.py, running session46403 for30min from~11:27. Forwards only loopback host6200 advertisements to B6113 and A127.0.0.2:6112. Host remains PID5792. No remote server, main game, installer or kora changes.
- Current lab is Own Save Control running both restored heroes. Continue cross-player autosave normalization research; preserve freshpair originals for per-client diff and known-good control. Do not overwrite these with host copies. Installer remains deferred.

## 2026-10-16 11:57 host autosave view probe (latest)
- Added research-only PROBES[8] in native/build_state_probe_map.py. After LRBT, a zero-delay LVPF timer resets CHHV/OVO from GetLocalPlayer and reapplies existing FogEnable/Mask settings. It never disables fog or shares vision. Eight map builder tests passed. Not a production fix.
- Lab-only LoD View Probe.w3x SHA256 f55f90997cbebb854109f15c438168516aa5e025659aea3d16554b1cbd60d77b. Created View Refresh Probe; A Tuskarr, B Leshrac, both level1. Force-killed owned B21232 at11:50:44. A autosave GHost++ AutoSave View Refresh Probe (ZEVB).w3z is4632077bytes SHA2567531b3d35157a32a57b61a97f60884ca32ccf1a5172215e8f159d226695238e1. Complete decompression verified.
- Copied exact host bytes to both Save/Multiplayer/viewhost.w3z. Closed previous match and A; restarted both, A10920 window657894, B23264 window984482, controller session54989. Exact replay GHost++ 2026-10-16 11-51 View Refresh Probe (04m26s).w3g. New saved lobby Host View Restore loaded both11:55:31 (A3.04s,B5.05s). This is both-client saved-session reload, NOT live single-client rejoin.
- Probe8 did NOT repair B vision: B selects Leshrac and has HP511/mana338/resources, but Scourge base/hero are dark/invisible; top-left hero icon remains A's Tuskarr. No View probe diagnostic text observed (could have expired; callback execution not established). Right-click(508,407) then later double-click portrait shifted camera terrain consistently with hero displacement, stronger movement evidence than previous test, but visible model and synchronized control acceptance still fail. Do not claim fixed.
- Next isolate load callback execution/local engine identity and fog/UI caches. Reapplying fog alone has not been demonstrated effective. Preserve original host autosave and known-good per-player freshpair saves; never use older B state as current checkpoint.
- ZEVB manual UI renaming is needed in this isolated two-process test because both use shared HKCU name and bypass MongolRanger. set_war3_player_name/inspect_and_patch_war3 support writing name, but authenticated account -> immutable match seat -> Rejoin integration is not complete. Product must not require manual renaming; do not promise current end-to-end behavior is already verified.
- Host remains local PID5792. Discovery session46403 expires around11:57; check before restarting. Current A/B are running Host View Restore. No remote/kora/installer changes.

## 2026-10-16 12:28 native view restoration: two host-save loads passed

Confirmed root cause and experimental fix:
- A copied host save maps B to the correct local player (7) but retains A's render/fog/UI caches. Before repair B had CGameWar3+0x28=7, +0x2c=2, fog masks [2,63,63], while B's actual vision-allies mask was4032. Correct B values are view128 and fog[128,4032,4032]. A is player1/view2/fog[2,63,63].
- Added tools/lab_memory_snapshot.py, accessed using the launch controller's existing child handle. OpenProcess on LoD fails; retained child handle works. tools/run_owned_lab_clients.py supports explicit inspect-LABEL-PID.request and reloads the diagnostic module per request. JASS-global inspection still fails its bounded-read guard; do not claim globals verified.
- Diagnostic field writes alone exposed terrain but did not fully restore units/UI. They are NOT the fix and must not be shipped. Fresh successful clients below had no repair marker/manual memory writes.
- Added native/build_view_restore_probe.py: exact-hash-pinned game.dll patch. At saved-session mapping epilogue RVA0x5c1232 preserve the original cookie check, flags/registers, set view mask from the already-remapped local player, and invoke Warcraft's own UI player-view switch RVA0x2fcb50. That native path rebuilds unit/UI/fog caches. Stub79bytes at RVA0x86c610, relative module-base calculation, original relocations and synchronization checks preserved. Supports active colours0..11 only; observer behavior untested.
- Original SHA2566d21bd9a0f9fbc8446f455c9e89ac994fed68174426fe608fcb9baefd4dec53c. Generic experimental output runtime/native/game-view-probe.dll SHA25685bfc5e589c171e45a1d5de3848b17bbfa7ccacdd0daa75d34b501a1379525a8. Installed ONLY into isolated lab plus its existing instance-event/UDP-port edits: A SHA25681041eab68acd2f8ba23237546db84c8ec44c839790e67144286a1553563766b, B SHA2560d5740c291c8994d0c988f60eab90dc4cae9cfee550a5cc315d5eacc166ab6ca. Do not rerun prepare_two_client_lab.py over these files.
- tests/test_view_restore_probe.py: two tests passed (unknown input rejected; change regions, branch destinations, relocation data and sync-check bytes preserved). Eight map-builder tests also passed. These are binary-boundary tests, not proof of every engine path.

Observed two-player results (user agreed to no input; agent issued the movement commands):
1. Native View Restore used IDENTICAL viewhost.w3z host autosave bytes on A28328/B25880, loaded12:17:57. B's top-left icon, visible Leshrac and Scourge vision restored. Explicit right clicks moved B from approximately(687,340) to(468,434), then to(753,315); subsequent screenshots confirmed arrival. A's Tuskarr moved from(592,300) to(838,280). Both level1, B HP511/mana338, A HP587/mana234. No permanent fog reveal or alliance modifications.
2. Forced owned B25880 to exit at12:22:17. A produced GHost++ AutoSave Native View Restore (ZEVB).w3z:4966373bytes,1341 complete blocks, SHA2562bbf1135430d6e6691776132ced2b7d6cc1823c9e439a26a2ea0cce4d93a17bf. Copied EXACT bytes to both Save/Multiplayer/nativehost.w3z; no header/perspective conversion. Ended old isolated match, then closed A and launched fresh A6436/B20300.
3. Native Crash Repeat loaded both12:24:56 (A3.06s,B5.01s), using original View Refresh Probe replay for the unchanged participant mapping; saved-session matches do not emit a new replay here. B's Leshrac visible after centering camera, moved from~(700,320) to(475,426), confirmed arrival. A Tuskarr retained its previous position and then moved from~(820,280) to(584,283), confirmed arrival. Readback inspect-A-6436.json and inspect-B-20300.json confirms correct masks for each player. Host log has no desync/drop through12:27; this is bounded observation, not a full-match test.

Limits and next work:
- This proves shared HOST autosave loading with visible, controllable own heroes, including a repeated forced-crash checkpoint. BOTH clients reload into a NEW saved lobby. Single returning client joining the unchanged live session is STILL NOT implemented; do not label this production Rejoin complete.
- Camera initially inherits host's location. Double-click own portrait centers correctly. Automatic own-hero camera centering remains to implement; view visibility and hero control themselves now pass.
- This is one modified LoD map, two opposing players and two level1 heroes; no item/spell/cooldown persistence acceptance,10-player test, host-PC outage, prolonged gameplay or other maps yet. Existing probe8 map remains in use; its standalone fog callback did not fix the issue. Native fix needs further isolation against the prior map fixture before distribution.
- Native patch is a research builder, not integrated with production patching/client/update/install flow. Camera fix, authenticated seat mapping, synchronized checkpoint/pause and checkpoint-to-live-session bridge remain. No remote deployment, kora change or installer this turn.
- Current live lab: hostPID5792 loopback6200/admin6201; A6436/window2427082, B20300/window1509020. Controller session13044 retains child handles. Relay session86561 expires around12:32. Native Crash Repeat still running; user can inspect. Marker force-crash-LABEL-PID.request terminates only exact owned child. Persistent sky wa/wb refer to these returned windows.


## 2026-10-16 13:22 checkpoint-to-live bridge: bootstrap works, synchronization fails
- Added recovery_lab/checkpoint_bridge.py, a loopback two-player experiment. Original A15464 remained in its ORIGINAL world after force-killing B16608. Replacement B9896 loaded the validated A checkpoint bridge_1792126694 via a separate loader lobby. No healthy-client reload occurred in this trial.
- Fixed loader handshake: replacement must receive GAMELOADED_OTHERS for BOTH participants, including itself, before simulation. Suppressing its own ready packet caused immediate disconnect. Separate loader advertisement receiver 127.0.0.3:6112 fixes discovery interference; bridge clients use6210, original host6200, loader6300.
- Extended wait works in this bounded observation (>15min): ping alone is insufficient; every25s STOP_LAG/zero-time empty action/START_LAG keeps Warcraft connected without simulation advancement. Native zero-time actions do not produce checksums. This is lab transport only, not product Add time UI or authenticated policy.
- Actual common-tick checksums did NOT match. Original check A9e7e6612/B ea3aab3d; native snapshots found25ms load clock gap. Normally advancing B25ms aligned both clocks to513625 but checks remained A2dd1602c/B011b0763. Read-only active-object inventory differs in84 slots, counts A35259/B35295. Do not bypass or rewrite checksums/counters. Diagnostic evidence preserved in runtime/two-client-lab/evidence-bridge-1792126694.
- Cannot yet claim only crashed player resumes synchronized gameplay. Loader bootstrap and original-client waiting are working pieces; checkpoint-to-live state normalization remains unresolved. LoD load callback creates/rebinds native/map state; investigate its state mutations and engine save boundary.
- Added PROBES[9] camera hook to native/build_state_probe_map.py: own local player's CGCH hero, ownership/observer guards, PanCameraToTimed, no timer/selection/vision mutation. runtime/native/LoD Camera Probe.w3x SHA37e236827c53133da3ef6f46fca7acdd215d0b1be7c78b8018644f434330492c. Static checks pass; live camera test follows, not yet established here. Existing saves embed old scripts and cannot test this new hook.
- Current diagnostic sessions are being closed explicitly before a fresh camera-map test; preserve their files. Do not mistake old PID references above for new current processes. No kora/remote/installer changes.

## 2026-10-16 14:28 — Camera passed; live checkpoint continuity still fails

User correction: use `-ar` for quick LoD tests, not `-random`; show both Warcraft windows during testing. Fresh LoD tests now use GHost HCL `ar` (`map_defaulthcl=ar`), which selected heroes/skills automatically. The separate engine control map intentionally has no LoD mode script. Screenshots of A and B were displayed repeatedly. No installer or production/remote/kora changes.

### Implemented and actually observed

- PROBE10 in native/build_state_probe_map.py reuses serialized FGCBO trigger LRFT and caches native module offsets LRVA/LRPA so load rebinding avoids temporary ability creation. `LoD Rebind Probe.w3x` SHA256 2dad4008d414cfd8447dcf695ea7e4f288d8908c8a7c7672e42eab980f928ca5. Did not fix live sync. Trial bridge_1792129058: clocks aligned156625ms, actual packet checks A2778dc2e/Bb89326c4; evidence preserved separately.
- PROBE11 defers own-hero camera centering to the first existing OVGVO periodic callback via serialized flag LRCP, instead of doing it inside LRBT while loading. No new timer, unit selection, vision reveal or alliance change. `LoD Camera Tick Probe.w3x` SHA256 0153162710f9642e1ed6fc4bc9a35b3fd6713997f53f5dde4ecef57d3bfb9216.
- Camera LIVE PASS in bridge_1792129708: fresh A25504 Vengeful Spirit and B10732 Kunkka (Captain Obvious). Agent moved B visibly before crash; moved A camera to midriver to distinguish perspectives. Force-killed only B10732 at13:52:09. Replacement B28208 loaded A checkpoint mr_d97e414afa6ace15f608 at13:53:38. B's visible Kunkka was automatically centered without portrait double-click or other centering input. A25504 stayed in ORIGINAL world. This proves own-camera restoration on the returning process, NOT synchronized continuation: actual first checks A5fb36d9c/Be81c385d still differed.
- PROBE12 reuses two additional OBFCO triggers (LROT/LRGT) while rebinding native callback handles on load. `LoD Reuse Callbacks Probe.w3x` SHA256 60ab926386f918225c377d3a91724b060059328d32a546f8ed444632428e6b9b. BUILT AND STATIC TESTED ONLY; not installed or live tested.
- Native view builder now has optional refresh_only=True: skips ownership-cycling loop at RVA2fcbf3 to tail2fccc6 while keeping fog/UI refresh. Generic runtime/native/game-refresh-only-probe.dll SHA256 4d59c17b8732a708b58f1622840527b3e60430fd66cc3046fbc084ab0390e5b6. B lab SHA ca10033cad3060be25c4475252ca96ea2ccec3f58acf68ee4583872d8564c940. B11628 loaded camera11 checkpoint with own visible centered Kunkka, but the same52 agent-index/type differences remained. This variant is research, not a proven replacement for the earlier two-client view patch.

### Engine control experiment and loader seed fix

- Added tools/build_recovery_control_map.py. Replaces war3map.j with a small script creating two heroes and resources, retaining the original map's slot config/terrain/object data. NO LoD bootstrap or load-event callbacks. It is not a pure Blizzard map: Hamg resolves to LoD Treant Protector; Hpal has default string text. PJASS compilation passed after retaining the original config and using native SetFloatGameState.
- `Checkpoint Engine Control.w3x` SHA256 615615f64a23932efec3209a8676c6c3c60ae42b8a543e82b6343a2c9a6059ae; lab config enginecontrol.cfg, empty HCL. Initial failed variants were not valid loaded-game tests.
- bridge_1792130574: A20888 remained in original world throughout. Original B14408 force-crashed14:05:25. Checkpoint bridge_1792130574.w3z / identical staged mr_c1d74755f525280c9d16.w3z.
- Refresh-only B11152 loaded; after25ms normal clock advance and a common100ms tick, both clocks41625, actual checks Aa17d5e9b/B31292ab0. Baseline native B27456 (only instance/UDP changes, NO view patch) also loaded; measured225ms gap aligned both to41825, actual checks Aa23e52ff/B4b3b77f8. Both native versions had120 agent-index/type differences: A22631/B22633 active objects. Thus the view patch or LoD callbacks alone do not explain all divergence.
- Found GHost's separate saved-game lobby uses a new m_RandomSeed instead of checkpoint seed. Added restore_lobby_seed for strictly validated SLOTINFOJOIN/ SLOTINFO packets, preserving every other field; setup_loader reads seed from the exact validated checkpoint. This is match metadata restoration, not a checksum rewrite.
- Read-only TLS component inspection found all45 random streams differed with the loader's new seed. With checkpoint seed108488197, B12340 and then B22628 had44/45 streams IDENTICAL to survivor A20888. Only stream index2 differs. Direct checksum component3 digest A4ff79154/B4ff34558. This improvement reproduced on two separate returning processes, but continuation still failed.
- Final aligned B22628 trial: advance measured525ms via normal empty action, wait for its REAL ack, then send both a common100ms frame. Native clocks both42125ms, actual packet checks Acde23e7d/B3801d60f. Gate stays MISMATCH. No commands were released as successful resumed play.
- Final handle table A {1c:22642,40:22513,50:22643}; B {1c:22693,40:22492,50:22704}. Agent inventory has rebuilt listener/agent identities. Do NOT simply overwrite allocator counters: the corresponding object graph would also need consistent identities.
- Evidence: runtime/two-client-lab/evidence-bridge-1792130574/comparison.json plus snapshots A20888/B11152/B27456/B12340/B22628 and bridge log. Earlier camera and rebind trials have their own evidence directories.

### Bridge/diagnostic changes and cautions

- checkpoint_map_config selects the UNIQUE config matching the save's embedded map path; rejects missing/ambiguous matches. Fixes helper accidentally using default lod.cfg for a probe save. Added --fresh-map for isolated fresh tests; this does not replay match history.
- Bounded measured clock adjustment accepts only integer25ms multiples, >0 and <=1000, only frozen MISMATCH and both connected. AlignmentGate records only the returning participant's actual ack, always returns None (never opens play), then a NEW two-participant CheckpointGate compares the common tick. Tests reject invalid gaps, wrong participant/stale ack, timeout, and unfrozen operation.
- Hot reload caveat: replacing Bridge class DOES NOT replace already-running read-loop coroutines / server's originally bound handler. An intermediate ALIGNING phase edit was not recognized by the old coroutine; B12340's ack was counted but not gated, causing timeout/disconnect. That trial is NOT a valid aligned comparison. Fixed by using existing VERIFYING packet path with separate AlignmentGate. B22628 repeated the alignment successfully (real ack then common comparison), still mismatch. Changes to existing read loops should normally be tested with a fresh bridge.
- tools/lab_sync_components.py queries only owned process/thread memory; verifies WoW64 TEB self pointer and PID/TID, finds engine TLS index45/system13 checksum components. No process writes or injected calls. Several map-table cached digests match. Native stream digest at280c80 and seed source confirmed from pinned disassembly (debug string `Random val: %u`).
- tools/lab_hash_emulator.py runs copied native checksum code in Unicorn2.1.4 installed ONLY in runtime/tooldeps. Bounded pages/instructions/time; no real game execution or memory writes. Thirteen component methods evaluate; slots6 and19 fail bounded checks (null read/external target) and must NOT be reported as verified. Tests confirm emulated writes never alter source bytes, missing memory/external execution reject, infinite loops stop.
- IMPORTANT: checksum component2 at sync-manager+2278/+4 changes during waiting even without simulation clock advancement. Snapshots are taken AFTER packet checks; do not invert earlier packet checks using later component2 values or conclude all unexplained difference is real world divergence. Need capture component inputs at the exact checksum boundary to isolate remaining differences. Likewise copied-memory emulation is diagnostic, not an accepted state check.
- Last validation: 28 targeted tests passed (bridge, native view bounds, map transforms, emulator isolation). These are not live recovery acceptance or installer readiness.

Remaining required work: preserve/reconstruct current RNG stream2 and required engine identity/state at the exact checkpoint boundary, including load-created agent identities; capture frame-exact components to distinguish actual simulation state from history/cache differences; then repeat the ORIGINAL acceptance test with only crashed LoD player loading, both heroes moving/using items and spells synchronously. Do not bypass checks or replace the task with replay-from-start or mandatory reload of all clients. Authenticated seat/Rejoin/AddTime UI, host-PC outage,10-player and full-match tests remain unimplemented/unverified.

End-of-trial cleanup: preserved snapshots/log/comparison before closing exact owned A20888/B22628 via their retained child handles. Stopped only bridge24252 and its helper24084 after checking command line/parent/path. Original host5792 and MongolRanger were left running. Restored B/Game.dll from the temporary baseline to the previous movement-tested view patch, verified SHA2560d5740c291c8994d0c988f60eab90dc4cae9cfee550a5cc315d5eacc166ab6ca. A remains SHA25681041eab68acd2f8ba23237546db84c8ec44c839790e67144286a1553563766b. No current live A/B game or bridge remains; persistent sky wa/wb are stale and must not be reused. All checkpoints retained. Next test requires fresh owned clients/bridge, not hot-reloading a nonexistent session.

## 2026-10-16 15:23 frame-exact trace and real RNG restoration (still NOT resumed)
- Added native/build_sync_trace_probe.py: pinned original binary, .mrtrace RW section at BB5000; component hook5e49 and final checksum-store hook5458f9 copy actual inputs to32-record ring. No checksum/clock/allocator modifications. Unit emulator validates original registers, flags and result preserved.
- Installed initial traced native files only in lab: A6040dab58b0c2d55d50b995cad345939d0d0e611395bc60eefbfa5dfbf5b6183; B32929600a7e6789fb3406f22e259df29102a7a542d96aefe02a2ec87e219e0f1. Original game and remote/kora untouched.
- Live bridge_1792133965, original A27888 and B24440, Camera Tick Probe11 map/HCL ar. Before crash26 overlapping recorded clocks matched ALL components and actual checksum. A Sorceress, B Tauren. Force-crashed only owned B24440; A remained in original game waiting, generated checkpoint mr_c81220a7d87155a2daa1.w3z, seed111878871.
- B19540 loaded that save while A stayed unchanged. Own Tauren visible and auto-centered without portrait click. Initial check A1b2b6f33/B088310bc (packet byte order) FAILED. Measured25ms clock gap; normal25ms step B followed by100ms common tick aligned trace clocks46225ms. Checks still differed. Exact components only2(network event history) and3(RNG) differ; streams2,8,21 differ. Others incl actual player/script component methods match.
- Disassembly debug strings537e30/9584f0 identify component2 as syncNetEventChecksum. Writer5530d0 processes native network events, adds byte-hash contribution at5533ba. This is transport/event history, not proof of world-state equality. Its difference remained31076 between clients over a later common frame.
- Added tools/lab_rng_restore.py: explicit one-shot restore-rng-PID.request consumed by owned snapshot controller. Requires exact PID, named SHA256-pinned donor snapshot, phaseMISMATCH, both recorded and current clocks equal, unchanged sequence/RNG data, unique native component address; writes ONLY360 actual RNG bytes and audits before/after/readback. This is a lab research transfer, NOT production sidecar integration. Never writes checksums/clocks/allocator counters. Initial request safely rejected because native checksum is computed BEFORE the100ms frame advances clock; updated guard separately validates recorded and current clocks.3 validation tests pass.
- Applied real donor A RNG state to B19540 at current46325ms (trace46225), then new real100ms common tick. ALL45 streams and component3 matched afterward. Only component2 remains different among captured component digests. Actual checks still A0xbb6219d1/B0x491ef921 at trace46325ms, gateMISMATCH. Original checksum code unmodified; no movement/orders released.
- Handle metadata still differs: A count33654/free33404/serial40079; B count33654/free29625/serial40138.56 active index/type differences. B has32 additional active objects (28 CAgentBaseAbs +4 CPoFlag);12 CPoReThresholdLis shifted indices. Do NOT overwrite allocator counters to hide this. Added bounded read-only per-PID inspect-objects request to capture exact selected object headers.
- Evidence runtime/two-client-lab/evidence-bridge-1792133965 includes before/after trace snapshots, detailed headers, RNG audit, log and comparison.json (explicit FAIL). Camera/visibility pass does NOT prove controlled resumed movement.
- Bridge added compare_frozen_tick diagnostic: only2 connected MISMATCH clients, fresh gate, common100ms and two actual acknowledgments required. Trigger bridge-comparison.request plus reload_lab_code.14 bridge+RNG tests pass.4 native telemetry tests pass, including optional allocation trace described below.
- Added optional allocations=True trace: hook480687 captures last256 script-agent wrapper creations with object pointer/type tag and bounded native stack sample (clamped to fs:StackBase). It preserves native mov/pop instructions and flags/registers. No allocation mutation. Data section extends0x17000; allocation ring offset7000; reader tools/lab_sync_trace.py.
- B19540 was closed through exact retained owned handle after evidence capture. B now installed runtime/native/game-sync-alloc-B.dll SHA2478e819065efe8be0d4558d67fd7827349fc5a4b71e0c01a397a08a35036748, allocations stub86c750. New owned B12772 (session37343), window395926, is loading the same checkpoint as of15:23. Original A27888/window264604/controller1806 remains waiting. Bridge session47588 still running; helper was recreated via validated bridge repair. Current snapshots must be re-read; new B has NOT received RNG transfer yet.
- Next: read allocation_trace after B12772 loads; correlate extra wrapper objects with actual call stacks, then fix duplicate/recreated load objects and restore required checkpoint metadata. Probe12 (reuse two OBFCO triggers) exists but not live tested; current map remainsProbe11. Entire one-player return acceptance remains FAILED, installer deferred.


## 2026-10-16 16:02 — Probe12 tested, complete checksum inputs isolated (NOT resumed)

- Continued the two-player local acceptance test with user authorization. No production/kora/server/installer changes. Used HCL ar. User confirmed no keyboard/mouse interaction during this trial.
- Before this trial, filtered allocation trace B23988 on the earlier Probe11 checkpoint showed 21 additional handler registrations (283 vs304), new sequential code keys287..307. Shared handler indices retained the same code keys. Evidence is in evidence-bridge-1792133965/callback-allocations.json. Old A27888/B23988 and old bridge15160/helper16376 were ended only after evidence capture.
- Installed Probe12 LoD Reuse Callbacks Probe.w3x (SHA60ab926386f918225c377d3a91724b060059328d32a546f8ed444632428e6b9b) in both lab folders and host/maps, mapcfg reusecallbacks with HCL ar. Reuses two OBFCO triggers LROT/LRGT; this reduces some duplication but does NOT solve continuation. Native lab A remains6040dab58b0c2d55d50b995cad345939d0d0e611395bc60eefbfa5dfbf5b6183; B filtered allocation trace85d86a5dcac0d0f9449d7bd23fb0f8911b66610034d9e6c4366514453c87d600.
- Fresh bridge_1792136151/session13459: original A28136/window9242424 (Axe), B11320 (Alchemist). 19 overlapping baseline trace clocks matched all captured components AND actual checksums. Force-crashed only owned B11320. A28136 remained in its original world, autosave mr_ff8d5d5247a1ee042c9d.w3z, seed114064493.
- Replacement B14192/session39536/window2623876 loaded the host checkpoint. Alchemist visible and camera automatically centered without portrait click; original host remained waiting. Initial actual checks A f7835cd9/B a5946b34 (packet byte order) failed. Advanced B25ms normally, awaited real ack, then both100ms: trace clocks58925 equal, numeric checks A0xaa62af22/B0xc0522216, still fail. First frozen handler counts273/289, then292 after subsequent frame callbacks; don't compare different-time counts as exact duplicate reduction. Final active-index/type differences46.

### Newly found auxiliary RNG state and exact reconstruction
- Pinned native disassembly545840 uses: folded registered component digests, constant17ab, clock (or full-agent hash when enabled), handle free-list head (fallback count), allocation serial, and an auxiliary8-byte state digest from pointer game+AB73D8 via280be0.
- IMPORTANT stack detail: native pop edi at5458e7 shifts ESP; the next XOR uses serial, NOT free-list head a second time. The final XOR uses the auxiliary digest. Added tools/lab_checksum_report.py with offline reconstruction; unit test executes ORIGINAL545840 in an isolated Unicorn machine to verify this formula including free==-1 fallback and rejects unavailable full-agent hashing. It never changes a game.
- AB73D8 first8 bytes are actual generator state: initialized by4ab660, advanced by11390. It is separate from the45 TLS streams. Native LoadGame5c11f1 reinitializes it with a seed. Probe12 aligned A bytes5706d94b8454984c vs B6d7ccc06b0743414. Adding this input reconstructed BOTH actual checks exactly, resolving the previously unexplained checksum remainder.
- tools/lab_memory_snapshot.py now reads sync_auxiliary_state (bounded8 bytes). tools/lab_rng_restore.py optional restore_auxiliary true validates both snapshots reconstruct native checks, equal recorded/current clocks, exact targetPID and sequence, donorSHA, unchanged current bytes. Transfers the REAL360 stream bytes plus REAL8 auxiliary bytes; no checksum/clock/allocator/identity writes. Audit separately records partial stream/auxiliary success. For MRT2 snapshots it also rejects auxiliary state advanced since trace.
- Applied real state transfer to B14192 at trace58925/current59025. Donor trace-donor-A-28136.json SHA7684954dbc57728f7744f3c06ae5c4c20f17e5b31a9bab859a3f20368ab7b42e. Both writes/readbacks succeeded. Next common100ms frame: trace59025 both, ALL45 streams and auxiliary state match. Only component2 (network-event history) differs. Actual checks A0x5169bc3d/B0xa50beded still FAIL. Their entire XOR difference is explained by component2 contribution0xf5800010, free-list-head contribution0x01e25c00, serial contribution0x00000dc0. No missing checksum input remains for this observation, but this is not a full-world equivalence proof (full_agent_hash==0).
- Final metadata is recorded in evidence-bridge-1792136151/comparison.json with explicit acceptance FAIL. Baseline/first/aligned/RNG-restored snapshots, callback allocations, RNG audit/donor and bridge log preserved there. Orders have NOT been released as successfully resumed play.

### Diagnostic updates and tests
- Native sync trace builder now produces MRT2 records adding exact component aggregate, auxiliary digest and8 raw bytes at the packet boundary; reader remains compatible with MRT1. Stack capture preservation validated by emulator tests. This updated builder is TESTED but NOT installed into the running clients (they still use MRT1). Do not overwrite their mapped DLLs or claim the current trial used MRT2.
- 40 targeted tests passed (bridge, native telemetry preservation/allocation bounds, RNG validation, checksum native emulation, map transforms, view patch, isolated emulator). Follow-up RNG/checksum6 tests passed after adding MRT2 current-vs-recorded state rejection. These are NOT full-match acceptance.
- Current running A28136/window9242424 and B14192/window2623876 are frozen in MISMATCH, bridge session13459, original host5792. Owned A controller2486 and B controller39536 retain child handles for1h from launch; inspect-<label>-<pid>.request and force-crash-<label>-<pid>.request are scoped to these handles. Sky wa/wb currently refer to these windows, but refresh actual process/window state before reuse. Preserve checkpoints before ending the trial.
- Remaining: reconstruct allocator/free-chain/object identities consistently and restore network-event checkpoint history as part of a valid restore protocol. Merely changing counters or substituting checksums is NOT a solution; the object graph and future allocations must agree. Then repeat acceptance with original healthy host never reloading, only crashed client loading, and both heroes moving/casting/using items synchronously. Authentication/seat identity, product Rejoin/AddTime, host-PC outage,10-player/full-match tests remain unfinished.
