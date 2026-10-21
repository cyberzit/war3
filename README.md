# MongolRanger — Warcraft III 1.26a Open Source Reconnect Host Service & LAN Lobby Client

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Platform: Windows 7/8/10/11](https://img.shields.io/badge/Platform-Windows%207%20%7C%208%20%7C%2010%20%7C%2011-blue.svg)](https://github.com/cyberzit/war3)

**MongolRanger (`war3`)** is a free, open-source Warcraft III: The Frozen Throne (1.26a) multiplayer hostbot, crash-reconnect engine, W3GS room relay, and universal Windows desktop launcher (`Windows 7 / 8 / 8.1 / 10 / 11`).

- **Repository:** [https://github.com/cyberzit/war3](https://github.com/cyberzit/war3)
- **Author / Maintainer:** `cyberzit` (`cyberzit@gmail.com`)
- **License:** Open Source — [MIT License](./LICENSE)

## Key Open Source Components
- **`backend/`**: FastAPI W3GS Room Hostbot (`w3gs_room.py`), multiplayer state sync, reconnect checkpoint coordinator, and web portal (`app.py`, `public_ui.py`).
- **`core/`**: Local UDP/TCP W3GS LAN proxy, P2P tunnel, WarKey hotkey remapper (`warkey.py`), and automatic crash recovery manager (`recovery_manager.py`).
- **`native/` & `recovery_lab/`**: Native Warcraft III 1.26a `Game.dll` save/load state restoration and deterministic reconnect research tools.
- **`dist_packages/installer.nsi`**: Universal NSIS installer script supporting Windows 7 SP1 through Windows 11 (x86/x64).

---

## Research & Architecture Notes

Status: **local feasibility prototype & live W3GS reconnect host service**.
An experimental installer has been built; it does not include working crash recovery.
Installer work is paused at the user's request until recovery is validated.

## Required outcome

### Current priority, 2026-10-13: seamless return after process loss

Native investigation started on the installed hash-pinned binary, without making
new backup copies (as requested). `native/inspect_save_load.py` identifies JASS
registration references and follows MSVC RTTI pointer structures. Static results:
SaveGame wrapper RVA 0x3bbee0, LoadGame wrapper RVA 0x3bbe60; the second registration
table binds both to a zero-return stub at 0x71d9d0 and must not be mistaken for the
real implementation. LoadGame calls candidate RVA 0x3a4c70, SaveGame calls candidate
0x3af8d0. Both wrappers check 0x3b28c0 first; its meaning is not yet established.
CSaveGame type descriptor leads to a candidate vtable at RVA 0x93e93c; its methods
include buffered data access, not an established whole-world restore operation.

`CloseTrace.cs --save-trace` adds five entry probes (wrappers plus three candidate
callees), retaining the existing network probes. The x86 SaveLoadTrace build
launched the installed game, verified and armed 21 breakpoints, then ended its
owned child after 15 seconds. Evidence: runtime/save-load-arming-20261013.jsonl.
The initial smoke check is now followed by real LoD save/load experiments below.
Static discoveries and disassembly are in runtime/native/save-load-*.
No game binary on disk was patched in this step.

#### LoD save/load experiment, 2026-10-13

The installed LoD map explicitly disables Save through `OOHCO`: it clears the
Save/Overwrite button callbacks and NOPs two engine call sites. Its only active
invocation is `ExecuteFunc("OOHCO")`. `native/build_state_probe_map.py` removes
only that invocation in a separately named research map, `LoD State Probe 2.w3x`.
The original map SHA-256 is pinned, encrypted MPQ sectors are round-trip checked,
and other archive member bytes remain identical. `mpyq==0.2.5` is installed under
runtime/tooldeps. The first, oversized `LoD State Probe.w3x` was rejected at LAN
join and is not the active research map. Probe 2 keeps the original archive size.
The host runner accepts `--map 'Maps\Download\LoD State Probe 2.w3x'`.

With only the menu blocker removed, Save crashes reproducibly at game.dll
RVA 0x42939a: the array serializer reads address zero with element count
0xffffffff. The caller is the script variable serializer at 0x459a61.
The forged header is `ffffffff ffffffff 00000000`, used by LoD's memory API.
Evidence: runtime/save-load-unblocked-20261013-01.jsonl and
runtime/save-load-fault-20261013-01.jsonl (registers and fault address included).

`CloseTrace.cs --save-array-probe` is a diagnostic workaround, not a release fix.
At 0x429389 it changes only EDI to zero when that exact header and the expected
script-serializer caller match. It writes an empty array payload while leaving
the live array header untouched. Two matching visits produced a 4,612,430-byte
`Save/Multiplayer/LabProbeD.w3z`; the running game continued afterwards.
Evidence: runtime/save-array-probe-20261013-01.jsonl. Save SHA-256:
adc0cbc6b834378027816a165f73515d5de13d05329d382db8c9fb7f4128dc7f.

Fresh-process LAN Load recognizes the save and reaches game actions, but then
crashes at 0x2dd056 reading address 0x30. This is the original `GetUnitCount`
native: LoD redeclares it as a memory reader, but its runtime replacement has
not been rebound after loading. LoD's `HCOC` originally installs read/write
stubs and sets `CHBV` / `CGOV`; those booleans survive while the hooks do not.
Evidence: runtime/load-array-probe-20261013-01.jsonl. No successful restored
play, checksum match, healthy-client continuity, or instant reconnect is claimed.
Next prerequisite: rebuild LoD's native bindings, virtual arrays, and external
allocations after load without preserving stale process addresses. Merely
skipping access violations or returning zero would hide incorrect game state.

`--load-memory-probe` reproduces the map's GetUnitCount/AttackMoveXY memory
stubs in the owned process. It gets past the first fault, then fails in the
unrebound IgnoredUnits native (RVA 0x2dce86). A read-only JASS global inspection
at dispatcher RVA 0x45d181 confirms BOO/BGO have size zero, while cached native
fields and trampoline addresses retain old process values. Inspect before
0x45d187: that instruction overwrites the EBP-0x0c VM local with 1.
Evidence: runtime/load-globals-probe-20261013-03.jsonl. Global layouts were
cross-checked against the local YDWE hashtable/global_variable sources.

`--load-rebind-probe` additionally allocates a new 50,000-byte executable arena,
relocates 43 explicitly named arena globals, clears VFO flags and six native
binding caches, and recreates BOO/BGO memory aliases. It is restricted to the
hash-pinned LabProbeD fixture and game binary, and modifies process memory only.
The live experiment reached an actual native table update (0x0253399c to
0x1ad203e8), passing the original AI-native faults. It then crashed at RVA
0x022ab6, dereferencing a null vtable through object address 0x21d84cbc.
Evidence: runtime/load-rebind-probe-20261013-02.jsonl. This demonstrates partial
bootstrap reconstruction, not playable restoration or multiplayer equivalence.
Other cached object pointers, code patches, allocations and callbacks remain
unhandled. Next: inspect trampoline targets/arguments and compare with a fresh
initialized LoD process. The failed inspection runs are retained as diagnostics;
they are not successful restoration evidence. All 29 Python tests still pass;
the x86 diagnostic compiled and was exercised in the live experiments.

CGameState root cause (static + live, 2026-10-13): the 0x022ab6 null-vtable fault
comes from LoD's 0.1s periodic timer `OVGVO` (started at map init). `OVGFO` reads
`[game.dll+0xAB6EA4+0xC]+4`: 0xAB6EA0 is `InstanceGenerator<CGameState>` (RTTI,
created by 0x85e870 with element size 0x350), and +0xC is its first storage
slot. In a fresh process that slot holds the only CGameState (vtable RVA
0x94f6e4). After Load, the pre-load CGameState has been destroyed and that slot
is the allocator free-list head (+0x10), so the map passes a freed object to
0x4299e0. The engine's own live reference is `CGameWar3+0x1c`, where CGameWar3
is `[game.dll+0xAB65F4]` and 0x3a8060 is its lazy getter.
LoD's init-only `OVGBO(true)` also patches 0x42fcd5 (engine call to 0x4299e0)
to `ret 4`; CCV/BHV/BGV survive Load but the code patch does not.

`--load-rebind-probe` now (a) re-applies that 8-byte OVGBO patch after verifying
the saved original bytes, and (b) at 0x4299e0 replaces ECX with the live
CGameState only when ECX equals the allocator free-list head, is not a
CGameState, and the live object is one. Diagnostic process-memory only.
Live result: LabProbeD loaded in a fresh process and kept running with no
access violation; the LoD tavern/pick screen updated, and two new local orders
were accepted (journal `action_parser_call` at 02:50:09/02:50:17 UTC) and the
simulation responded (pick/skill command card appeared). Evidence:
runtime/load-gamestate-probe-20261013-01.jsonl and its `-screens` folder.
Map-side fix: `python native/build_state_probe_map.py 3` writes `LoD State Probe 3.w3x`
(SHA-256 dc0bd65f…e2a9). Besides the OOHCO removal, `OVGFO` now returns
`[[CBH+0xAB65F4]+28]-4` (live CGameState). To stay within the script's archived
span, the never-called debug printer `TestPrintAllTimers` is dropped. A new LAN
game on Probe 3 (one easy computer) was saved as `LabProbeE.w3z` (SHA-256 ae6df124…aea5,
runtime/save-probe3-20261013-01.jsonl). Loading it in a fresh process
(`--load-rebind-probe LabProbeE <sha>`) ran 300 s with 0 access violations and
0 debugger ECX rebinds: the map passed the live CGameState itself. A skill-draft
pick was accepted after load. Evidence: runtime/load-probe3-20261013-01.jsonl and
its `-screens` folder. The debugger still supplies the memory natives, the 43 arena
globals, BOO/BGO, native caches and the OVGBO code patch. Two-client checksum
equality and rejoining a live match remain unproven. 30 Python tests pass.

Debugger-free load (Probe 4, 2026-10-13): `python native/build_state_probe_map.py 4`
adds `LRBT`, registered in main on EVENT_GAME_LOADED. It resets the process-local
state a loaded game inherits (CHBV/CGOV/GHC false; VFF/FVF true; native rebind
caches BVH/BBH/BGH/OCG/HOG/FHF; 51 GetProcAddress caches; cached string pointers
OGH/OFH; map-grid pointer HVCO). It then reruns LoD's own bootstrap `BVBC`
(memory API forge, game.dll addresses, new executable arena, HCOC native stubs,
helper DLL). Finally it reapplies main's patches (OBBFO/OBBGO/OBHBO/OCOOO, the
FGC/FFC patch, OVGBO). Four never-called debug functions are dropped so the
script keeps its archived span. Iterations:
- `GHC` was missing at first: the observe-only debugger run crashed in
  GetTownUnitCount (runtime/load-probe4-observe-20261013-01.jsonl, map now
  `LoD State Probe 4a.w3x`).
- With GHC reset: observe-only run, 300 s, 0 faults
  (runtime/load-probe4-observe-20261013-02.jsonl, map `4b`).
- Plain war3.exe then crashed in strlen on a stale cached string pointer (OGH/OFH),
  which the debug heap had hidden. Crash text:
  runtime/load-probe4a-plain-crash-20261013.txt.
- Current Probe 4 (SHA-256 83460096…606d) with save `LabProbeH.w3z`: **plain war3.exe,
  no debugger attached**, loaded and ran about 6 minutes with no crash report. A
  draft skill pick was accepted and the game continued past the pick phase.
  Screens: runtime/load-probe4-plain-20261013-01-screens.

Still debugger-dependent: creating the save (virtual-array serializer workaround,
`--save-array-probe`). Hooks LoD enables later in a game (e.g. FixAllCyclones,
key/packet hooks) are not yet reapplied on load. A spawned hero's control,
two-client checksums and a live rejoin are unverified. 31 Python tests pass.

Debugger-free save and runtime hooks (Probe 6, SHA-256 c6542…d476, 2026-10-13):
- `LSAV` runs on EVENT_GAME_SAVE. It finds the BOO/BGO array objects through the
  JASS global table at `GFOC(1)+0x285c` (VM pointer confirmed with
  `CloseTrace --vm-probe`, runtime/vm-probe-20261013-01.jsonl). It zeroes their
  header fields so they save empty. A 0 s timer (`LRSV`) restores the forged
  values, but only if OBVO matches, so a restored timer after load is a no-op.
- First attempt crashed after saving: the restore called GFOC, which reads
  through the un-forged BOO (runtime/probe6a-plain-save-crash-20261013.txt).
- LRBT now also reruns FCVHG (LoD's 0.01 s hook installer). Its game-state parts
  (FCFVG/FCFGG id lists, quests, 15th-slot report) stay init-only. LRBT also runs
  the HHCBO settings steps (HHGVO, HHCGO, HHCVO 1-4). main's FGC/FFC patch is no
  longer applied, because FCVHG's BGVC undoes it.
- Result, all with plain war3.exe and no debugger: `LabProbeL.w3z` saved (SHA-256
  8af51603…f84b), the game kept running and finished its skill draft, and a hero
  could be picked. In a fresh process the save loaded and the skill draft
  completed. A hero (Faceless Void) was bought and moved by a right-click order.
  Screens: runtime/probe6-plain-save-load-20261013-screens.
- Open issue: after that save (and the hero pick), the game menu greyed out Save
  Game for the rest of the session (screen l6.png). The cause is not yet known.
  Repeated autosaves need it.

Repeatable saves (Probe 7, SHA-256 110c4ffb…d706): the greyed-out Save Game
comes from the engine, not LoD. Evidence: `--menu-probe`, runtime/menu-probe-20261013-0{1,2,3}.jsonl.
- The menu routine (0x3500a0) disables Save when 0x53ef80 returns 0, which
  happens when the local player's entry field +0x3c is non-zero.
- A DR0 write watch found the only writer is 0x53ef40, called from the save
  command handler at 0x43f08c with `lea edx,[eax+1]`. That is a per-player save
  counter.
- `LSVN` (run at init and from LRBT) changes that byte to `lea edx,[eax]`, only
  after verifying the original dword 0x01508D52.
- Plain war3.exe, no debugger: LabProbeQ1 and LabProbeQ2 were saved in the same
  game and Save stayed enabled. LabProbeQ2 was loaded in a fresh process and saved
  again as LabProbeQ3 (SHA-256 24401bb5…a49e), and the game continued. No crash
  reports. Screens: runtime/probe7-repeat-save-20261013-screens.
- Every client must run the same map patch. Whether the counter matters for
  multiplayer save sync is untested.

Still unverified: hooks LoD toggles later in a game; handle-id effects of LRBT's
extra triggers when only one client loads; two-client checksums; a live rejoin.
33 Python tests pass.

The user considers whole-match autosave/restart too disruptive and again wants
the host PC to keep the match, wait with a countdown on disconnect, and restore
only the missing player at the paused simulation point. Session recording may
be temporary and deleted after confirmed match completion. Historical diagnostic
evidence is not authorized for deletion by this future retention preference.

Research conclusion: hosting and buffering on a player's PC are feasible and
partly implemented, but a command log is not a directly loadable world state.
GProxy++ documents network-loss recovery with the Warcraft process still alive,
buffered message acknowledgments, and synchronized empty actions for extending
wait time. It does not establish recovery of a terminated Warcraft process.
Source: https://github.com/w3gh/gproxyplusplus and the local upstream readme.

The decisive unproven capability is restoring a complete simulation checkpoint
inside a fresh 1.26a client, retaining its player identity and connecting it to
the existing match without resetting healthy clients. A private internal
checkpoint is different from forcing everybody through the Save/Load UI; it
still needs a working capture/restore implementation. Host-side state may require
a surviving Warcraft simulation, not just GHost's command forwarding. Raw memory
copies and Windows Process Snapshotting are not evidence of resumable Warcraft
state across new processes: addresses, handles, threads, graphics, network state,
and script runtime must remain valid or be reconstructed.
Microsoft describes its API as process capture/inspection:
https://learn.microsoft.com/en-us/previous-versions/windows/desktop/proc_snap/overview-of-process-snapshotting

Next feasibility gate: capture a small known LoD scene with hero/items/timers,
restore only a fresh client while the other client stays loaded, compare both
simulation checksums and visible state, then issue new orders. If that cannot
be demonstrated, do not promise immediate crash recovery. Existing accelerated
replay plus longer waiting remains a fallback, not equivalent to the requested
behavior. Replacing the game's network architecture with an authoritative
server/client implementation is a much larger engine project, not a proxy fix.

### Earlier alternative: synchronized save and restart (now deprioritized)

The user now explicitly accepts interrupting every player and restarting the
whole match from a save when one game process fails. This is distinct from the
previous seamless return requirement and should be evaluated before more native
snapshot reverse engineering.

Upstream GHost++ documents multiplayer save/load and disconnect autosave:
https://github.com/ghostBot/ghostplusplus (Using Saved Games).
Local source confirms `EventPlayerDeleted` sends action 0x06 with a save filename
before the player-leave notification when `bot_autosave` is enabled and the leave
code is DISCONNECT. Remaining Warcraft processes create the saves; GHost itself
does not serialize game state. Saved hosting supports `loadsg`, `enforcesg` and
`hostsg`, with original player PID/slot mapping recovered from the first replay.

Critical limitation documented upstream: the already crashed player cannot
create its own new save. Saves are player-specific; copying another player's
save can cause incorrect fog and other glitches, even with a same-team donor.
Therefore do not claim that after-crash autosave alone is sufficient.

Research path for that earlier alternative: coordinate periodic saves while all clients are alive,
record per-player save files and original identities/slots as one checkpoint,
and commit it only when every participant confirms a complete local file. Keep
the previous complete checkpoint if any participant fails during saving. After
a crash, use the last complete checkpoint, accepting bounded rollback. Confirm
save completion and checkpoint availability before leaving any surviving game.
Reload the same map/build with each player's own save and original slot. Automate
lobby return only after manual save/load succeeds on DotA LoD 6.85m with two real
clients. Save cadence, load time, map-script behavior, file validation, and
repeated recovery remain untested. No autosave settings were enabled by this
research and existing user save files were not modified.

Windows application for Warcraft III TFT 1.26a / build 6401, primarily DotA LoD
6.85m. A player's computer runs the host service. Friends connect through clients.
Recovery must also work after Warcraft III exits with a fatal error and is restarted,
not only after an internet outage. Keep the host service and client proxy separate
from the game process. Voluntary Leave Game is not treated as a crash.

## What exists

- `recovery_lab/host.py`: prepares a separate loopback-only GHost++ runtime,
  reads the user's LoD map without modifying it, creates a private LAN room,
  and can transfer room ownership to a player. No Battle.net account is used.
- `recovery_lab/protocol.py`: W3GS framing, join identity, LAN advertisements,
  and client synchronization checksum parsing.
- `recovery_lab/proxy.py`: experimental local proxy. Records the server/client
  transcript and retains the host TCP connection if the local game disappears.
  Attempts to bootstrap a fresh game process with the recorded lobby and action
  stream. Discards duplicate client acknowledgments and old commands. Compares
  recorded client checksums, and closes the replacement connection on mismatch.
- `recovery_lab/sync.py`: checksum gate, including fail-closed mismatch handling.

The experiment intentionally uses ordinary W3GS with `bot_reconnect = 0`.
It does not implement GProxy++ internet reconnect, GPS empty-action handling,
NAT traversal, authentication, internet rooms, an installer, or host failure recovery.
Retaining a socket does not prevent the server's lag timeout or a player drop.
Transcript/checksum handling is an experiment, not proven game-state restoration.
The JSONL journal is diagnostic; it cannot recover a crashed proxy or host.

## Inspection and live test, 2026-10-12

Installation:
`D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III`.

- `war3.exe` and `game.dll` report 1.26.0.6401; the running game's menu agrees.
- Map: `Maps\Download\DotA LoD 6.85m.w3x`.
- Existing crash reports date from 2008–2012 and identify other machine paths.
  They do not establish the cause of the user's current fatal errors.
- GHost++ 17.2 loaded this map and calculated its map metadata and ten slots.
- The custom `[LAB] LoD Recovery Lab` advertisement appeared in the actual game.
- The actual Warcraft client joined through the proxy and loaded LoD successfully.
- A live session supplied 566 client synchronization checksums.
- The first one-player session ended at GHost++'s 60-second gameover timeout.
  The lab controller now adds a GHost++ fake player to avoid that timer in a
  one-client feasibility test. This correction is not yet verified in a live game.
- A controlled process stop from the development shell returned Access Denied.
  Therefore no process death was simulated by that attempt.
- Further UI testing could not proceed: the Windows control helper reported user
  input in the game window and a minimized-window state. No successful fresh-process
  catch-up, no actual fatal-error recovery, and no multi-player recovery is claimed.
- Protocol/checksum unit tests pass; these do not establish in-game recovery.
- All lab host/proxy processes launched by the development shell were stopped.

## Forced-close test and follow-up diagnostics

The user ended the test Warcraft process through Task Manager. The development
agent verified that the process was absent, the proxy retained its server socket,
and GHost++ displayed lag for the original player. The recorded pre-disconnect
session contains 2,688 client synchronization checksums.

The agent relaunched Warcraft, joined the same LAB room with the same name, and
observed `reconstruction_started`. The replacement client disconnected before
producing a synchronization checksum. The live host subsequently dropped the
player after its lag timeout. **Live crash recovery failed in this test.**

To isolate startup ordering, `recovery_lab/offline.py` replays the pre-disconnect
transcript without a live host. Waiting for the replacement client's map-load
confirmation before forwarding player-load notifications allowed the map to load,
but the client still disconnected at simulation time zero. A second diagnostic
with paced packet delivery also failed, without any replacement checksums.
The root cause is unresolved. No hero/item restoration, live catch-up, or gameplay
control was verified. The recorded transcript and failed diagnostic logs remain
in `runtime/session.jsonl`, `runtime/offline-unpaced.jsonl`, and
`runtime/offline.jsonl`. These are local diagnostic files, not distributable game data.

Next work is to locate the bootstrap/protocol failure before another live test.
Offline diagnostics cannot establish successful online recovery.

## Latest investigation / handoff

The ordinary-speed offline diagnostic produced **208 consecutive replacement
checksums matching the original session**. It disconnected when replay cursor 244
delivered an original local-player command associated with selection in this test:
`f70c150064004aca020a001b01ff570000af860000` (PID 2, action 0x1b).
CRC32 low-word validation of that incoming packet passes. This narrows the failure
to processing a historical command rather than a corrupt captured packet.

The replacement generated the same first three automatic outgoing action bodies
as the original process. It had not generated the fourth, manual selection command.
The exact semantics of action 0x1b on this build have not been established.
This supports, but does not prove, a mismatch in the client's local command/echo
state. Native command validation and queue layout have not been confirmed.

Added an acknowledgment window (four action ticks) to avoid flooding the client,
map-load notification gating, first-action startup delay, TCP EOF diagnostics,
action-group CRC/length validation, and an optional local-command echo diagnostic.
`python -m recovery_lab.offline --require-local-echo` waits for old own commands to
be reproduced. It reached the same selection command with 208 matched checks and
remained waiting instead of immediately disconnecting. A manual click happened
after Warcraft had entered its host-wait screen; the old command was not reproduced,
and the diagnostic timed out. This is not a successful recovery result.

An isolated omission experiment replaced only that 0x1b command's action packet
with an empty tick of the same duration. It failed at **checkpoint 209**. Therefore
discarding that command does not preserve the recorded state/checksum sequence.
This probe was diagnostic only; command omission is not implemented as a recovery
feature. The source transcript is unchanged.

Additional preserved diagnostic files:
`runtime/offline-traced.jsonl`, `runtime/offline-delayed.jsonl`,
`runtime/offline-realtime.jsonl`, `runtime/offline-local-echo.jsonl`, and the latest
`runtime/offline.jsonl` (omission probe). All shell-launched lab servers were stopped.

Read-only process inspection of the running Warcraft process returned Windows
error 5 (Access Denied), even for limited-query access. The new
`recovery_lab/client_launcher.py` is a lifecycle probe, not a finished launcher.
An attempted query through its child handle returned error 299; that child had
already exited while a pre-existing Warcraft instance remained, so its process
inspection result is inconclusive. No game memory was patched, no DLL was injected,
and no Windows security settings were changed.

Read-only research checkouts were added under `engines/ydwe` and
`engines/memhack-api`. They are reference material, not installed plugins or runtime
dependencies. `runtime/tooldeps` contains pefile/capstone for static binary
inspection. The game installation has not been edited.

Next: establish how the 1.26a native client accepts/replays its own command stream
and preserves its checksum state, with controlled fresh-process diagnostics. Do
not equate the Python diagnostic queue with the game's actual native queue. Keep
all simulation checks enabled. A separate client module may be required, but that
has not been proven or implemented. Only then repeat live host recovery, hero/items,
two real clients, and actual fatal-error tests before building the Windows installer.

## Reproduce the local experiment

### Fresh-process follow-up

A repeat baseline with a freshly launched, visible Warcraft process again stopped
at replay cursor 245 with 208 matching checkpoints. The Warcraft process remained
running and showed the map; this observed failure is a connection closure, not an
observed fatal process crash. Evidence:
`runtime/offline-20261011T224930415827Z.jsonl` (UTC filename; October 12 locally).
A second local-echo diagnostic stopped before command 244. A UI click did not
produce the required outgoing command before the host-wait screen, so it does not
establish the command's semantics or validate the native-queue hypothesis.
Evidence: `runtime/offline-20261011T225210747650Z.jsonl`.

The owned CreateProcess handle successfully enumerated modules and read the MZ
header of game.dll at 0x6f000000 in a clean launch. Ordinary OpenProcess still
returned error 5. This establishes read access through the launcher, not knowledge
of the game's command queue. The launcher now enumerates existing war3.exe
processes before launching, including processes that cannot be opened for queries.
It refuses duplicate-process diagnostics. All game processes and offline servers
started during these follow-up tests were stopped.

Offline diagnostics now use unique timestamped journals by default. Use
`--journal PATH` to specify an output, and `--interval 0.1` to reproduce the paced
baseline. A source transcript cannot be used as its own output journal.
Full restart recovery remains unresolved; no installer-ready release exists.

Requires Python 3.11+ and the cloned upstream repositories under `engines/`.
The GHost++ executable also needs x86 Visual C++ 2010 runtime DLLs. During setup,
the signed Microsoft redistributable was extracted into `runtime/vc2010`; the
needed DLLs were copied only into `runtime/host`, without a system installation.
`Storm.dll` is copied from the upstream StormLib directory by `prepare()`.

Run `python -m unittest discover -s tests -v` for protocol checks.

Use `python -m recovery_lab.run --player ZEV` to start the lab host, create the
LoD room, start the proxy, and assign that player ownership after they join.
Python must run from this project directory. If needed, replace `ZEV` with the
name entered in Warcraft's LAN screen; names must be 1–15 ASCII characters.

In Warcraft, open Local Area Network and join **[LAB] LoD Recovery Lab**.
After the controller adds a fake player and assigns ownership, type
`!start force` in the lobby. This test is local-only. Do not invite friends yet.

Once game state is established, a local test control on TCP 6211 accepts exactly
`disconnect-local-for-test\n` to close the local client socket while retaining
the host socket. This tests a local disconnect followed by a fresh process; it
does not reproduce a real fatal error. Restart Warcraft and join the same cached
LAB room with the same name. The journal must show reconstruction and matching
checksums before any success claim. Stop the experiment if reconstruction fails.

## Native modification authorization and staging

The user explicitly authorized changes to the game code. This permits research
on native client integration; it does not establish that a working fix exists.
`python -m recovery_lab.native_workspace` preserves SHA-256 verified copies of
war3.exe, game.dll and Storm.dll under `runtime/native/originals`, and separate
unmodified research copies under `runtime/native/working`. `manifest.json` records
source paths, hashes and both copies. This is not a runnable cloned installation.
Staging refuses to overwrite an existing modified copy. Original installation
binaries have not been patched. The lifecycle diagnostic now saves the actual
loaded module paths to support native investigation.

## Desktop client and installer prototype

`client/RecoveryClient.cs` builds with the Windows .NET Framework C# compiler.
The x64 WinForms client launches a selected war3.exe and offers six inventory key
bindings (default Z/X/C/V/B/N to numpad 7/8/4/5/1/2). Remapping starts disabled,
is limited to the launched game's foreground process, ignores injected events,
and releases synthetic keys on focus loss or shutdown. F12 disables remapping.
Chat suppression tracks Enter and Escape; it is a heuristic, not native chat-state
integration. Mouse-opened chat, menus, and other input fields are not detected.
In-game key behavior still requires validation. The client does not yet host or
join network rooms and has no functioning crash reconnect.

`recovery_lab.bundle` stages only an explicit list of game binaries, four MPQs,
the LoD map, and this client. It omits unrelated executables, archives, logs and
user configuration from the original game directory. Staged bytes are verified
with SHA-256; the manifest explicitly marks the result not release-ready.
`installer/LoDClient.iss` creates a per-user installation and shortcuts. Inno Setup
6.7.3 was downloaded from the official jrsoftware GitHub release, its Authenticode
signature verified, and its compiler installed under `runtime/inno`.

The desktop client compiled and its window opened/responded/closed in a smoke
check. The staged game launched and its game.dll was readable. These checks do not
prove installation on a clean machine, hotkey correctness, or multiplayer recovery.
The installer is `dist/LoDRecovery-Prototype-Setup.exe` (799,974,939 bytes).
The desktop client currently targets x64 Windows with .NET Framework 4; 32-bit
Windows is not supported by this client build. The packaged game is still the
original 1.26a binary, with no native reconnect patch applied.
The generated installer successfully installed into `runtime/install-check`;
all 11 installed payload files matched their SHA-256 manifest. Its uninstaller
then returned success. This is a same-machine installation test, not a clean-PC
compatibility test. The Python test suite now contains 21 passing tests.

## Release validation

User-assisted test 2026-10-12 09:04 local: FAILED for the 5m22s game.
The original process had 3,178 recorded checksums when terminated. Replacement
matched 1,386 without a mismatch, but GHost dropped ZEV after its 60-second lag
timeout and closed the retained connection. No successful recovery is claimed.
Evidence: `runtime/session-20261012T005749705373Z.jsonl`,
`runtime/audit-user-test-01.json`, `runtime/close-trace-user-test-original-01.jsonl`
and `runtime/close-trace-user-test-restored-01.jsonl`. Extend host recovery waiting
with correct lag-screen keepalives and/or accelerate reconstruction before asking
the user to repeat a longer game. Verify elapsed history BEFORE terminating it.

Native diagnosis: `native/CloseTrace.cs` is an x86 debugger that launches only its
own Warcraft child. It checks the exact game.dll SHA-256, verifies 14 closesocket
call instructions, and installs temporary in-memory breakpoints. It logs call
sites, registers, raw stack bytes and exceptions, restores the instruction for
single stepping, and terminates its own child when finished. Disk binaries are
not changed. This is an observational diagnostic, not a reconnect fix. Software
breakpoint timing can affect execution; other threads can pass an unarmed site
during the single-step interval, so the trace is not exhaustive.
The launch/arming smoke check passed. Reconstruction tracing located a receive
callback rejection at the first absent historical local selection command.
Read-only static inspection identified the RTTI name
`CNetCommandUnitSelectionEvent`, its vtable at preferred address 0x6f932cfc,
and a sender at RVA 0x2cc350 that sets command ID 0x1b. The field deserializer
at RVA 0x554320 reads one byte and two dwords, consistent with the captured
10-byte action including its ID. `native/inspect_selection.py` regenerates this
hash-pinned disassembly, including incoming action validation at RVA 0x67e3d0.
The native parser compares an incoming local player's command with its own
previously sent command queue. A fresh process lacks historical manual commands.
With no matching entry, the branch at RVA 0x67e704 rejects the packet unless an
internal flag is set. `--replay-probe` replaces that conditional branch with an
unconditional jump **only in the owned diagnostic process's memory**, after
verifying the original bytes. Packet CRC and simulation checksum comparisons
remain active. This is an offline experiment, not a production patch: restoring
the branch and reconciling pending local commands at live handoff are unresolved.
The resumed probe passed all 2,688 historical checkpoints twice. With 100 ms
packet pacing, join-to-delivery took 281.488 seconds; with 5 ms pacing and a
four-update window, it took 93.168 seconds. Both received 2,702 checksums in total:
the additional 14 correspond to host updates already in flight at the original
process loss and are not covered by the original checksum oracle.

Evidence: `runtime/offline-20261011T231541087383Z.jsonl` (latest attempt),
`runtime/offline-echo-fast.jsonl`, and corresponding native
`close-trace-echo-resumed.jsonl` / `close-trace-echo-fast.jsonl` traces.
The original advertisement/transcript pair is copied to
`runtime/baseline-20261012` before starting another host.

A short **single real client plus fake player** live test also returned to the
retained GHost session after force-terminating the original process. The new
process matched 136 historical checkpoints, delivered the growing transcript in
11.410 seconds from join, and the host logged `stopped lagging on [ZEV]`.
More than 1,800 subsequent checksums arrived after live handoff. After returning,
the player purchased Fire Lord (gold 2,187 to 1,937), then issued a ground-move
order: both the returned host action and visible hero movement were observed.
The hero was purchased AFTER recovery; pre-existing hero/item restoration is
not proven by this test. Evidence is
`runtime/session-20261011T234358753502Z.jsonl`, `runtime/host/console.log`, and
`runtime/close-trace-live-original.jsonl` / `close-trace-live-restored.jsonl`.
This test retained the experimental branch change for the entire replacement
process. It does not establish two-client synchronization, hero/item restoration,
long-game catch-up, repeated restarts, or production readiness.

The native diagnostic optionally accepts a fifth argument, a fresh restore-marker
path. When that file appears it uses DebugBreakProcess to stop the owned child's
threads, verifies the patched bytes and restores the original conditional branch.
The control build compiled and its runtime smoke test logged
`historical_echo_validation_restored`; the game remained responsive at its main
menu. Evidence: `runtime/close-trace-restore-smoke.jsonl`. This verifies code
restoration only, not restoration during active reconstruction. Queue cleanup
at live handoff remains unproven. The original game.dll SHA-256 is unchanged.

Validation at this milestone: 26 Python tests passed. All owned diagnostic game
and host processes were stopped after recording results. Two-computer testing
availability has been requested from the user. Installer work remains paused.

`python -m recovery_lab.audit JOURNAL` independently compares the latest attempt
with the original pre-disconnect checksum history. It requires all historical
checksums and the transcript-delivered event before declaring its limited check
complete. It does not certify hero state, restored control, or live multiplayer.
Errors occurring after the complete historical comparison are reported separately
so deliberate process teardown does not erase an already completed comparison.
All new proxy journals use exclusive creation; default live journal names include
a timestamp. `offline --advertisement PATH --source PATH` can use an archived
advertisement/transcript pair after another live host is started.
Microsoft debugger-loop reference:
https://learn.microsoft.com/en-us/windows/win32/debug/writing-the-debugger-s-main-loop

The staged installation showed a missing base sound service during its first
visible launch; sound dependencies need investigation before a release. This
does not change the priority: prove reconnect before rebuilding the installer.

Prove fresh-process restoration on this build/map with two real game clients:
establish hero, items and resources; stop one process; restart it; verify recorded
checksums, both clients' current game state, restored control, continued updates,
and repeat after a longer game and repeated restarts. Test an actual fatal error
separately: replaying a deterministic map bug could trigger the same crash again.
Only after this passes should internet reconnect and the Windows product shell
be built around it. A save/rehost fallback would restart everyone from a save,
and would not meet seamless return to an ongoing match.

## Upstream references

- https://github.com/ghostBot/ghostplusplus
- https://github.com/w3gh/gproxyplusplus
- https://www.microsoft.com/en-us/download/details.aspx?id=26999

Upstream files and licenses remain in their original repositories. No Warcraft
binaries, maps, CD keys, or credentials are distributed by this project.
