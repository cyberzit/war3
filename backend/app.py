"""Isolated MongolRanger lobby, W3GS crash-reconnect coordinator, Map Catalog & Admin API."""
import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager, contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from backend.admin_ui import ADMIN_HTML
from backend.map_catalog import process_map_bytes
from backend.public_ui import PUBLIC_HTML
from backend.r2_storage import (
    is_r2_configured,
    normalize_r2_key,
    presign_r2_url,
    upload_bytes_to_r2,
)
from backend.w3gs_room import (
    LOD_MAP_CRC,
    LOD_MAP_HEIGHT,
    LOD_MAP_INFO,
    LOD_MAP_PATH,
    LOD_MAP_SHA1,
    LOD_MAP_SIZE,
    LOD_MAP_SIZE_INT,
    LOD_MAP_WIDTH,
    W3GSRoomManager,
    default_lod_slots,
)

DB_PATH = Path(os.environ.get("MONGOLRANGER_DB", "mongolranger.sqlite3"))
W3GS_PORT = int(os.environ.get("MONGOLRANGER_W3GS_PORT", "8051"))
ADMIN_USER = os.environ.get("MONGOLRANGER_ADMIN_USER", "admin")
ADMIN_DEFAULT_PASS = os.environ.get("MONGOLRANGER_ADMIN_PASS", "MongolRanger2026!")
SESSION_SECONDS = 7 * 86400
ROOM_SECONDS = 120
rate_lock = threading.Lock()
db_lock = threading.RLock()
rate_events = defaultdict(deque)
password_slots = threading.BoundedSemaphore(2)
w3gs_manager = W3GSRoomManager()


def get_maps_dir() -> Path:
    custom = os.environ.get("MONGOLRANGER_MAPS_DIR")
    if custom:
        p = Path(custom)
    else:
        p = DB_PATH.resolve().parent / "maps"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_downloads_dir() -> Path:
    custom = os.environ.get("MONGOLRANGER_DOWNLOADS_DIR")
    if custom:
        p = Path(custom)
    else:
        p = DB_PATH.resolve().parent / "downloads"
    p.mkdir(parents=True, exist_ok=True)
    return p


DEFAULT_DOWNLOAD_SLOTS = [
    {
        "slot": "client_win",
        "title": "ZevArena Тоглоомын Програм (Windows .EXE)",
        "platform": "Windows 7 / 8 / 8.1 / 10 / 11 (32-bit & 64-bit — Бүх хувилбарт ажиллана)",
        "version": "v4.8 .EXE Installer",
        "description": (
            "ZIP задлах шаардлагагүй! Татаад 2 дармагц Windows-ийн бүх хувилбар (Windows 7, 8, 8.1, 10, 11 • 32-bit ба 64-bit) дээр шууд сууж ажилладаг албан ёсны .EXE суулгагч. "
            "Шинэ v4.8 Esport интерфэйс, 3 минутын Crash Reconnect, 3 давхар Anti-MapHack, WarKey болон ELO чансааны систем багтсан."
        ),
        "filename": "ZevArena-Setup.exe",
        "external_url": "",
        "size_label": "265 KB",
        "button_text": "Суулгагч Татах (.EXE)",
    },
    {
        "slot": "game_full",
        "title": "Warcraft III: Frozen Throne 1.26a + DotA Багц",
        "platform": "Windows 7 / 8 / 10 / 11 (Шууд тоглоход бэлэн • Cloudflare R2 CDN)",
        "version": "1.26a Албан ёсны",
        "description": (
            "Суулгах шаардлагагүй, задалж шууд тоглоход бэлэн Warcraft III 1.26a үндсэн тоглоом "
            "болон албан ёсны 5 үндсэн DotA / LoD газрын зургуудын бүрэн багц (Cloudflare R2 өндөр хурдны CDN)."
        ),
        "filename": "Warcraft-III-1.26a.zip",
        "external_url": "r2://mongolranger/downloads/Warcraft-III-1.26a.zip",
        "size_label": "847 MB",
        "button_text": "Warcraft III 1.26a Татах",
    },
]


@contextmanager
def database():
    with db_lock:
        db = sqlite3.connect(DB_PATH, timeout=30.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA temp_store=MEMORY")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()


def _default_lod_meta() -> dict:
    return {
        "filename": "LoD_Sync_25.w3x",
        "title": "DotA v6.85m LoD (Reconnect)",
        "author": "DracoL1ch",
        "map_path": LOD_MAP_PATH,
        "file_size": LOD_MAP_SIZE_INT,
        "sha256": "e8954a9c753a55b16e0bbb4bf239a3598139bca20176b1bd3233802573ecb45a",
        "map_size": list(LOD_MAP_SIZE),
        "map_info": list(LOD_MAP_INFO),
        "map_crc": list(LOD_MAP_CRC),
        "map_sha1": list(LOD_MAP_SHA1),
        "map_width": list(LOD_MAP_WIDTH),
        "map_height": list(LOD_MAP_HEIGHT),
        "map_options": 96,
        "num_players": 10,
        "num_teams": 2,
        "slots": default_lod_slots(),
        "has_cam": True,
        "has_reconnect": True,
        "patched": False,
    }


def initialize():
    from backend.build_client_packages import build_packages

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    get_maps_dir()
    dl_dir = get_downloads_dir()
    try:
        build_packages(dl_dir, overwrite=False)
    except Exception:
        pass
    with database() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA max_page_count=16384")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
          salt TEXT NOT NULL, password_hash TEXT NOT NULL, created REAL NOT NULL,
          last_seen REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions(
          token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS rooms(
          id TEXT PRIMARY KEY, owner TEXT NOT NULL UNIQUE REFERENCES users(id),
          name TEXT NOT NULL, map_name TEXT NOT NULL, capacity INTEGER NOT NULL,
          updated REAL NOT NULL, room_code TEXT NOT NULL DEFAULT '',
          launch_signal INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS members(
          user_id TEXT PRIMARY KEY REFERENCES users(id),
          room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS messages(
          id INTEGER PRIMARY KEY, room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
          user_id TEXT NOT NULL REFERENCES users(id), text TEXT NOT NULL, created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS message_room ON messages(room_id,id);
        CREATE TABLE IF NOT EXISTS friendships(
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          friend_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          status TEXT NOT NULL DEFAULT 'pending',
          created REAL NOT NULL,
          PRIMARY KEY(user_id, friend_id));
        CREATE TABLE IF NOT EXISTS blocks(
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          blocked_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created REAL NOT NULL,
          PRIMARY KEY(user_id, blocked_id));
        CREATE TABLE IF NOT EXISTS direct_messages(
          id INTEGER PRIMARY KEY,
          sender_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          receiver_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          text TEXT NOT NULL,
          is_read INTEGER NOT NULL DEFAULT 0,
          created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS dm_pair ON direct_messages(sender_id, receiver_id, id);
        CREATE TABLE IF NOT EXISTS room_invites(
          id INTEGER PRIMARY KEY,
          room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
          sender_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          receiver_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          status TEXT NOT NULL DEFAULT 'pending',
          created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS maps(
          id TEXT PRIMARY KEY,
          filename TEXT NOT NULL COLLATE NOCASE UNIQUE,
          title TEXT NOT NULL,
          map_path TEXT NOT NULL,
          file_size INTEGER NOT NULL,
          sha256 TEXT NOT NULL,
          meta_json TEXT NOT NULL,
          has_cam INTEGER NOT NULL DEFAULT 1,
          has_reconnect INTEGER NOT NULL DEFAULT 1,
          is_default INTEGER NOT NULL DEFAULT 0,
          created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS downloads(
          slot TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          platform TEXT NOT NULL,
          version TEXT NOT NULL,
          description TEXT NOT NULL,
          filename TEXT NOT NULL DEFAULT '',
          external_url TEXT NOT NULL DEFAULT '',
          size_label TEXT NOT NULL DEFAULT '',
          button_text TEXT NOT NULL DEFAULT 'Татах',
          updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_settings(
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_sessions(
          token_hash TEXT PRIMARY KEY,
          username TEXT NOT NULL,
          expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS hwid_registry(
          hwid TEXT PRIMARY KEY,
          last_user_id TEXT NOT NULL DEFAULT '',
          last_new_account_ts REAL NOT NULL DEFAULT 0,
          new_accounts_today INTEGER NOT NULL DEFAULT 0,
          last_abandon_ts REAL NOT NULL DEFAULT 0,
          last_abandon_user TEXT NOT NULL DEFAULT '',
          last_abandon_room TEXT NOT NULL DEFAULT '',
          total_abandons INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS match_history(
          id INTEGER PRIMARY KEY,
          user_id TEXT NOT NULL,
          room_name TEXT NOT NULL DEFAULT '',
          map_name TEXT NOT NULL DEFAULT '',
          result TEXT NOT NULL,
          kills INTEGER NOT NULL DEFAULT 0,
          deaths INTEGER NOT NULL DEFAULT 0,
          assists INTEGER NOT NULL DEFAULT 0,
          team INTEGER NOT NULL DEFAULT 0,
          teammates_json TEXT NOT NULL DEFAULT '[]',
          opponents_json TEXT NOT NULL DEFAULT '[]',
          elo_delta INTEGER NOT NULL DEFAULT 0,
          elo_after INTEGER NOT NULL DEFAULT 0,
          duration_sec INTEGER NOT NULL DEFAULT 0,
          created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_match_history_user ON match_history(user_id, id);
        """)
        for alter_sql in (
            "ALTER TABLE rooms ADD COLUMN room_code TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE rooms ADD COLUMN launch_signal INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE rooms ADD COLUMN no_leavers INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE rooms ADD COLUMN kicked_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE users ADD COLUMN last_seen REAL NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN elo INTEGER NOT NULL DEFAULT 1000",
            "ALTER TABLE users ADD COLUMN games_played INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN wins INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN losses INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN kills INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN deaths INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN assists INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN leaves INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN clean_streak INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN last_abandon_ts REAL NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN last_abandon_room TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN hwid TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN ping_ms INTEGER NOT NULL DEFAULT 12",
            "ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''",
        ):
            try:
                db.execute(alter_sql)
            except sqlite3.OperationalError:
                pass
        # Clean up any automated test/bot accounts so Leaderboard only shows real players
        db.execute(
            "DELETE FROM users WHERE name LIKE 'Host\\_%' ESCAPE '\\' "
            "OR name LIKE 'Peer\\_%' ESCAPE '\\' "
            "OR name LIKE 'test\\_%' ESCAPE '\\' "
            "OR name LIKE 'Smoke%' "
            "OR name LIKE 'bot\\_%' ESCAPE '\\'"
        )
        if not db.execute("SELECT 1 FROM maps LIMIT 1").fetchone():
            meta = _default_lod_meta()
            db.execute(
                "INSERT INTO maps VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "lod_sync_25",
                    meta["filename"],
                    meta["title"],
                    meta["map_path"],
                    meta["file_size"],
                    meta["sha256"],
                    json.dumps(meta),
                    1,
                    1,
                    1,
                    time.time(),
                ),
            )
        else:
            # Keep the built-in LoD_Sync_25 catalog entry in sync with the rebuilt map (CRC/SHA1/sha256 change).
            meta = _default_lod_meta()
            db.execute(
                "UPDATE maps SET file_size=?, sha256=?, meta_json=? WHERE id='lod_sync_25' AND sha256<>?",
                (meta["file_size"], meta["sha256"], json.dumps(meta), meta["sha256"]),
            )
        db.execute("DELETE FROM downloads WHERE slot='client_mac'")
        for d in DEFAULT_DOWNLOAD_SLOTS:
            row = db.execute("SELECT title, filename, external_url FROM downloads WHERE slot=?", (d["slot"],)).fetchone()
            if not row:
                db.execute(
                    "INSERT INTO downloads VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        d["slot"],
                        d["title"],
                        d["platform"],
                        d["version"],
                        d["description"],
                        d["filename"],
                        d["external_url"],
                        d["size_label"],
                        d["button_text"],
                        time.time(),
                    ),
                )
            elif d["slot"] == "client_win":
                db.execute(
                    "UPDATE downloads SET title=?, platform=?, version=?, description=?, filename=?, external_url=?, size_label=?, button_text=?, updated=? WHERE slot='client_win'",
                    (
                        d["title"],
                        d["platform"],
                        d["version"],
                        d["description"],
                        d["filename"],
                        d["external_url"],
                        d["size_label"],
                        d["button_text"],
                        time.time(),
                    ),
                )
            elif d["slot"] == "game_full":
                db.execute(
                    "UPDATE downloads SET title=?, platform=?, version=?, description=?, filename=?, external_url=?, size_label=?, button_text=?, updated=? WHERE slot='game_full'",
                    (
                        d["title"],
                        d["platform"],
                        d["version"],
                        d["description"],
                        d["filename"],
                        d["external_url"],
                        d["size_label"],
                        d["button_text"],
                        time.time(),
                    ),
                )
        guide_txt = (
            "⏱️ [КОМАНДЫН ЗААВАР] -start (Эхлүүлэх) • -1v1 -2v2 -3v3 -4v4 (Илүү суудал хааж 853g болгох) • "
            "-close 2 (Суудал хаах) • -openall (Нээх) • -swap 2 6 (Суудал солих) • -rmk (5м дахин эхлэх) • -gg (Бууж өгөх) • -addtime (+1м хүлээх)"
        )
        for r_row in db.execute("SELECT id, owner FROM rooms").fetchall():
            has_g = db.execute(
                "SELECT 1 FROM messages WHERE room_id=? AND text LIKE '⏱️ [КОМАНДЫН ЗААВАР]%' LIMIT 1",
                (r_row["id"],),
            ).fetchone()
            if not has_g:
                db.execute(
                    "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
                    (r_row["id"], r_row["owner"], guide_txt, time.time()),
                )


@asynccontextmanager
async def lifespan(app):
    initialize()
    try:
        await w3gs_manager.start_tcp_server("0.0.0.0", W3GS_PORT)
    except OSError:
        await w3gs_manager.start_tcp_server("127.0.0.1", 0)
    try:
        yield
    finally:
        await w3gs_manager.stop_tcp_server()


app = FastAPI(title="MongolRanger lobby", version="0.4.0", lifespan=lifespan,
              docs_url=None, redoc_url=None)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errs = exc.errors()
    msg = "⚠️ Мэдээллээ бүрэн, зөв оруулна уу."
    if errs:
        first = errs[0]
        loc = [str(x) for x in first.get("loc", [])]
        etype = str(first.get("type", ""))
        if "username" in loc:
            if "short" in etype or "missing" in etype:
                msg = "⚠️ Тоглогчийн нэр 2–24 тэмдэгт байх ёстой."
            elif "long" in etype:
                msg = "⚠️ Тоглогчийн нэр 24 тэмдэгтээс хэтрэхгүй байна."
            else:
                msg = "⚠️ Тоглогчийн нэр буруу тэмдэгт агуулсан байна."
        elif "password" in loc or "new_password" in loc:
            if "short" in etype or "missing" in etype:
                msg = "⚠️ Нууц үг хамгийн багадаа 6 тэмдэгт байх ёстой."
            elif "long" in etype:
                msg = "⚠️ Нууц үг хэт урт байна."
            else:
                msg = "⚠️ Нууц үгээ зөв оруулна уу (6+ тэмдэгт)."
        elif "email" in loc:
            msg = "⚠️ И-мэйл хаягаа зөв оруулна уу (жишээ нь: name@gmail.com)."
        elif "name" in loc:
            msg = "⚠️ Өрөөний нэрээ оруулна уу."
    return JSONResponse({"detail": msg}, status_code=422)


@app.middleware("http")
async def bounds(request: Request, call_next):
    is_checkpoint = request.url.path.endswith("/checkpoint") or request.url.path == "/api/debug/dump"
    is_map_upload = request.url.path == "/api/admin/maps" and request.method == "POST"
    is_dl_upload = (
        request.url.path.startswith("/api/admin/downloads/")
        and request.url.path.endswith("/upload")
        and request.method == "POST"
    )
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            length = int(request.headers.get("content-length", "-1"))
        except ValueError:
            length = -1
        if is_dl_upload:
            max_bytes = 120 * 1024 * 1024
        elif is_map_upload:
            max_bytes = 32 * 1024 * 1024
        elif is_checkpoint:
            max_bytes = 16 * 1024 * 1024
        else:
            max_bytes = 8192
        if length < 0 or length > max_bytes:
            return JSONResponse({"detail": f"Body must be at most {max_bytes} bytes with Content-Length"}, 413)
    now = time.monotonic()
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    real_ip = fwd or request.headers.get("x-real-ip", "").strip() or (request.client.host if request.client else "unknown")
    auth_hdr = request.headers.get("authorization", "").strip()
    rate_subject = f"{real_ip}:{auth_hdr[-16:]}" if auth_hdr else real_ip
    is_auth = request.url.path.startswith("/api/auth/") or request.url.path == "/api/admin/login"
    category = "auth" if is_auth else "api"
    limit = 10 if category == "auth" else 1200
    with rate_lock:
        for key in list(rate_events):
            if not rate_events[key] or rate_events[key][-1] < now - 60:
                del rate_events[key]
        if len(rate_events) > 8192 and (rate_subject, category) not in rate_events:
            return JSONResponse({"detail": "Busy"}, 503)
        events = rate_events[(rate_subject, category)]
        while events and events[0] < now - 60:
            events.popleft()
        if len(events) >= limit:
            return JSONResponse({"detail": "Too many requests"}, 429, headers={"Retry-After": "10"})
        events.append(now)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=128, pattern=r"^[^\x00-\x1f\"\\]+$")
    password: str = Field(min_length=6, max_length=128)
    email: str = Field(default="", max_length=128)
    hwid: str = Field(default="", max_length=128)


class PasswordResetInput(BaseModel):
    username: str = Field(default="", max_length=128)
    email: str = Field(min_length=3, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)
    hwid: str = Field(default="", max_length=128)


class ChangeNameInput(BaseModel):
    new_name: str = Field(min_length=2, max_length=24, pattern=r"^[^\x00-\x1f\"\\]+$")


class AdminLoginInput(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class AdminPasswordInput(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class DownloadLinkInput(BaseModel):
    external_url: str = Field(default="", max_length=1024)
    version: str = Field(default="", max_length=64)
    size_label: str = Field(default="", max_length=64)
    button_text: str = Field(default="", max_length=64)


class R2PresignInput(BaseModel):
    filename: str = Field(min_length=1, max_length=256)
    content_type: str = Field(default="application/octet-stream", max_length=128)


class R2CompleteInput(BaseModel):
    r2_key: str = Field(min_length=1, max_length=512)
    filename: str = Field(min_length=1, max_length=256)
    size_bytes: int = Field(default=0, ge=0)
    version: str = Field(default="", max_length=64)


class RoomInput(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    map_name: str = Field(min_length=1, max_length=128)
    capacity: int = Field(default=10, ge=2, le=12)
    hcl: str = Field(default="", max_length=16)
    room_code: str = Field(default="", max_length=32)
    no_leavers: int = Field(default=0, ge=0, le=1)


class RoomJoinInput(BaseModel):
    room_code: str = Field(default="", max_length=32)


class RoomCodeInput(BaseModel):
    room_code: str = Field(default="", max_length=32)


class HeartbeatInput(BaseModel):
    ac_status: str = Field(default="ok", max_length=32)
    game_dll_sha256: str = Field(default="", max_length=128)
    violation: str = Field(default="", max_length=256)
    ping_ms: int = Field(default=0, ge=0, le=9999)


class ChatInput(BaseModel):
    text: str = Field(default="", max_length=500)
    message: str = Field(default="", max_length=500)


class TargetUserInput(BaseModel):
    target: str = Field(min_length=1, max_length=64)


class FriendRespondInput(BaseModel):
    target: str = Field(default="", max_length=64)
    requester: str = Field(default="", max_length=64)
    action: str = Field(default="", max_length=16)
    accept: bool | None = None


class BlockUserInput(BaseModel):
    target: str = Field(min_length=1, max_length=64)
    action: str = Field(default="block", max_length=16)
    block: bool | None = None


class InviteRespondInput(BaseModel):
    action: str = Field(default="", max_length=16)
    accept: bool | None = None


class SlotActionInput(BaseModel):
    action: str = Field(default="", max_length=32)
    slot: int = Field(default=0)
    target_slot: int = Field(default=0)
    map_name: str = Field(default="", max_length=256)


def _compute_elo_level(elo: int) -> tuple[int, str, str]:
    """Returns (level_1_to_10, tier_title, hex_color) for 100..5000 ELO."""
    e = max(100, min(5000, int(elo)))
    if e < 600:
        return 1, "LVL 1 • Bronze", "#94A3B8"
    if e < 900:
        return 2, "LVL 2 • Bronze", "#A1A1AA"
    if e < 1200:
        return 3, "LVL 3 • Silver", "#34D399"
    if e < 1500:
        return 4, "LVL 4 • Silver", "#10B981"
    if e < 1900:
        return 5, "LVL 5 • Gold", "#FBBF24"
    if e < 2300:
        return 6, "LVL 6 • Gold", "#F59E0B"
    if e < 2800:
        return 7, "LVL 7 • Diamond", "#38BDF8"
    if e < 3400:
        return 8, "LVL 8 • Diamond", "#818CF8"
    if e < 4200:
        return 9, "LVL 9 • Master Pro", "#F97316"
    return 10, "👑 LVL 10 • LEGEND", "#EF4444"


def _compute_user_reputation(u_row, now: float | None = None, viewer_id: str | None = None) -> dict:
    if now is None:
        now = time.time()
    keys = u_row.keys() if hasattr(u_row, "keys") else {}
    target_uid = str(u_row["id"]) if "id" in keys and u_row["id"] is not None else ""
    is_self_view = bool(viewer_id and target_uid and str(viewer_id) == target_uid)

    elo = max(100, min(5000, int(u_row["elo"] if "elo" in keys and u_row["elo"] is not None else 1000)))
    games = int(u_row["games_played"] if "games_played" in keys and u_row["games_played"] is not None else 0)
    wins = int(u_row["wins"] if "wins" in keys and u_row["wins"] is not None else 0)
    losses = int(u_row["losses"] if "losses" in keys and u_row["losses"] is not None else 0)
    kills = int(u_row["kills"] if "kills" in keys and u_row["kills"] is not None else 0)
    deaths = int(u_row["deaths"] if "deaths" in keys and u_row["deaths"] is not None else 0)
    assists = int(u_row["assists"] if "assists" in keys and u_row["assists"] is not None else 0)
    leaves = int(u_row["leaves"] if "leaves" in keys and u_row["leaves"] is not None else 0)
    created = float(u_row["created"] if "created" in keys and u_row["created"] is not None else now)
    last_abandon_ts = float(u_row["last_abandon_ts"] if "last_abandon_ts" in keys and u_row["last_abandon_ts"] is not None else 0.0)
    last_abandon_room = str(u_row["last_abandon_room"] if "last_abandon_room" in keys and u_row["last_abandon_room"] else "")

    lvl, lvl_title, lvl_color = _compute_elo_level(elo)
    is_calibrated = games >= 10
    total_attempts = max(1, games + leaves)
    completion_pct = int(round((games / total_attempts) * 100)) if (games + leaves) > 0 else 100
    avg_kills = round(kills / max(1, games), 1) if games > 0 else 0.0
    win_rate = int(round(wins * 100.0 / games)) if games > 0 else 0
    kd_ratio = round(kills / max(1, deaths), 2) if (kills or deaths) else 0.0
    kda_ratio = round((kills + assists) / max(1, deaths), 2) if (kills or deaths or assists) else 0.0
    if is_calibrated:
        elo_text = f"LVL {lvl} • {elo} ELO"
        visible_elo = elo
        visible_lvl = lvl
        visible_lvl_title = lvl_title
        visible_lvl_color = lvl_color
    else:
        elo_text = f"⏳ {games}/10 (5v5)"
        visible_elo = 0
        visible_lvl = 0
        visible_lvl_title = f"Түвшин тогтоох ({games}/10)"
        visible_lvl_color = "#38BDF8"

    recent_hopper = (now - last_abandon_ts) < 2700.0  # 45 minutes
    is_newbie = ((now - created) < 172800.0 and games < 5) or (games < 3 and leaves == 0)

    # Requirement #12: Leavers must NOT see their own Leaver badge; only OTHER players and Host see it so they can kick them!
    if is_self_view and (recent_hopper or leaves >= 10):
        visible_leaves = 0
        visible_pct = 100
        visible_abandon_room = ""
        if (now - created) < 172800.0 and games < 5:
            badge_type = "NEWBIE"
            badge_icon = "🌱"
            badge_short = f"🌱 Шинэ тоглогч ({games}/10)"
            badge_full = f"🌱 ШИНЭ ТОГЛОГЧ (Түвшин тогтоох {games}/10 тоглолт)"
            badge_color = "#38BDF8"
        else:
            badge_type = "SHIELD"
            badge_icon = "🛡️"
            badge_short = "🛡️ Итгэлтэй (100%)"
            badge_full = f"🛡️ НОГООН БАМБАЙ • Итгэлтэй Тоглогч ({games} бүтэн тоглолт • 100%)"
            badge_color = "#10B981"
    else:
        visible_leaves = leaves
        visible_pct = completion_pct
        visible_abandon_room = last_abandon_room
        if recent_hopper:
            badge_type = "HOPPER"
            badge_icon = "🚨"
            badge_short = f"🚨 Хаяж гарсан ({leaves} Leave)"
            badge_full = f"🚨 САЯ ТОГЛОЛТ ХАЯЖ ГАРСАН («{last_abandon_room or 'Өмнөх өрөө'}» • Нийт {leaves} Leave)"
            badge_color = "#EF4444"
        elif leaves >= 10:
            badge_type = "LEAVER"
            badge_icon = "⚠️"
            badge_short = f"⚠️ LEAVER ({leaves} Leave)"
            badge_full = f"⚠️ БАЙНГА ТОГЛОЛТ ХАЯГЧ LEAVER ({leaves} удаа дундаас гарсан)"
            badge_color = "#EF4444"
        elif is_newbie:
            badge_type = "NEWBIE"
            badge_icon = "🌱"
            badge_short = f"🌱 Шинэ тоглогч ({games}/10)"
            badge_full = f"🌱 ШИНЭ ТОГЛОГЧ (Түвшин тогтоох {games}/10 тоглолт)"
            badge_color = "#38BDF8"
        else:
            badge_type = "SHIELD"
            badge_icon = "🛡️"
            badge_short = f"🛡️ Итгэлтэй ({completion_pct}%)"
            badge_full = f"🛡️ НОГООН БАМБАЙ • Итгэлтэй Тоглогч ({games} бүтэн тоглолт • {completion_pct}%)"
            badge_color = "#10B981"

    return {
        "elo": visible_elo,
        "elo_level": visible_lvl,
        "elo_title": visible_lvl_title,
        "elo_color": visible_lvl_color,
        "elo_text": elo_text,
        "elo_display": elo_text,
        "is_calibrated": 1 if is_calibrated else 0,
        "placement_games": min(games, 10),
        "win_rate": win_rate,
        "kd_ratio": kd_ratio,
        "kda_ratio": kda_ratio,
        "kill_rate": avg_kills,
        "stats_line": f"🏆 Хожлын хувь: {win_rate}%  •  🗡️ K/D: {kd_ratio}  •  ⚔️ Дундаж килл: {avg_kills}",
        "games_played": games,
        "wins": wins,
        "losses": losses,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "avg_kills": avg_kills,
        "leaves": visible_leaves,
        "completion_pct": visible_pct,
        "clean_rate": visible_pct,
        "badge_type": badge_type,
        "badge_icon": badge_icon,
        "badge_short": badge_short,
        "badge_label": badge_short,
        "badge_full": badge_full,
        "badge_color": badge_color,
        "recent_hopper": 0 if is_self_view else (1 if recent_hopper else 0),
        "last_abandon_room": visible_abandon_room,
    }


def _record_match_history(db, user_id: str, wroom, result: str, k: int, d: int, a: int, team: int,
                          elo_delta: int, elo_after: int, now: float):
    """Stores one row per player per match for the 'last 10 matches' profile cards."""
    try:
        my_name = ""
        u = db.execute("SELECT name FROM users WHERE id=?", (user_id,)).fetchone()
        if u:
            my_name = u["name"]
        mates, opps = [], []
        stats = getattr(wroom, "player_stats", {}) or {}
        init_players_low = {p.lower() for p in (getattr(wroom, "initial_players", None) or set())}
        for pname, st in stats.items():
            if pname == my_name:
                continue
            pk = int(st.get("kills", 0))
            pd = int(st.get("deaths", 0))
            pa = int(st.get("assists", 0))
            if init_players_low and pname.lower() not in init_players_low and pk == 0 and pd == 0 and pa == 0:
                continue
            entry = {
                "name": pname,
                "kills": pk,
                "deaths": pd,
                "assists": pa,
                "left": bool(st.get("abandoned")),
            }
            (mates if int(st.get("team", 0)) == team else opps).append(entry)
        started = float(getattr(wroom, "match_started_at", 0.0) or 0.0)
        duration = int(now - started) if started > 0 else 0
        map_name = Path(str(getattr(wroom, "map_path", "") or "").replace("\\", "/")).name
        db.execute(
            "INSERT INTO match_history(user_id,room_name,map_name,result,kills,deaths,assists,team,"
            "teammates_json,opponents_json,elo_delta,elo_after,duration_sec,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                user_id, str(getattr(wroom, "name", "") or ""), map_name, result, k, d, a, team,
                json.dumps(mates, ensure_ascii=False), json.dumps(opps, ensure_ascii=False),
                elo_delta, elo_after, duration, now,
            ),
        )
        db.execute(
            "DELETE FROM match_history WHERE user_id=? AND id NOT IN "
            "(SELECT id FROM match_history WHERE user_id=? ORDER BY id DESC LIMIT 50)",
            (user_id, user_id),
        )
    except Exception:
        pass


def _placement_elo(wins: int, games: int, kills: int, deaths: int, leaves: int) -> int:
    """Initial ELO assigned once the 10 placement matches are complete (win rate + kill rate based)."""
    win_rate = wins * 100.0 / max(1, games)
    kd = kills / max(1, deaths)
    avg_k = kills / max(1, games)
    seed = 1000 + (win_rate - 50.0) * 6.0 + max(-200.0, min(200.0, (kd - 1.0) * 80.0)) + avg_k * 4.0 - leaves * 25.0
    return int(max(500, min(1800, round(seed))))


def _penalize_match_abandon(db, user_id: str, username: str, room_name: str, hwid: str = "", wroom=None):
    if wroom is not None:
        init_cnt = int(getattr(wroom, "initial_player_count", 0) or len(getattr(wroom, "peers", {}) or {}))
        if 0 < init_cnt <= 4:
            return
        peer_names_lower = {p.lower() for p in getattr(wroom, "peers", {}).keys()}
        if peer_names_lower and (username or "").strip().lower() not in peer_names_lower:
            return
    now = time.time()
    u_row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not u_row:
        return
    cur_elo = int(u_row["elo"] if "elo" in u_row.keys() and u_row["elo"] is not None else 1000)
    cur_leaves = int(u_row["leaves"] if "leaves" in u_row.keys() and u_row["leaves"] is not None else 0)
    games = int(u_row["games_played"] if "games_played" in u_row.keys() and u_row["games_played"] is not None else 0)
    user_hwid = (hwid or (u_row["hwid"] if "hwid" in u_row.keys() else "") or "").strip()
    # Before placement is complete there is no visible ELO; the leave is counted and reflected in the placement seed.
    new_elo = max(100, cur_elo - 50) if games >= 10 else cur_elo
    new_leaves = cur_leaves + 1
    db.execute(
        "UPDATE users SET elo=?, leaves=?, clean_streak=0, last_abandon_ts=?, last_abandon_room=? WHERE id=?",
        (new_elo, new_leaves, now, room_name, user_id),
    )
    if wroom is not None:
        st = wroom.player_stats.get(username, {}) if hasattr(wroom, "player_stats") else {}
        _record_match_history(
            db, user_id, wroom, "LEAVE",
            int(st.get("kills", 0)), int(st.get("deaths", 0)), int(st.get("assists", 0)), int(st.get("team", 0)),
            new_elo - cur_elo, new_elo, now,
        )
    if user_hwid:
        db.execute(
            "INSERT INTO hwid_registry(hwid,last_user_id,last_new_account_ts,new_accounts_today,last_abandon_ts,last_abandon_user,last_abandon_room,total_abandons) "
            "VALUES(?,?,0,0,?,?,?,1) "
            "ON CONFLICT(hwid) DO UPDATE SET last_user_id=excluded.last_user_id, last_abandon_ts=excluded.last_abandon_ts, "
            "last_abandon_user=excluded.last_abandon_user, last_abandon_room=excluded.last_abandon_room, total_abandons=hwid_registry.total_abandons+1",
            (user_hwid, user_id, now, username, room_name),
        )


def _check_and_penalize_abandon_on_leave(db, room_id: str, user_dict: dict):
    """Checks if the room being left is an active match that has been running for >= 90s; if so, penalizes the leaver."""
    now = time.time()
    room_row = db.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
    if not room_row:
        return False
    wroom = w3gs_manager.get_room(room_id)
    if not wroom:
        return False
    # Never penalize spectators/viewers who opened an already-started room via "Харах" and were not actual W3GS players
    uname = (user_dict.get("name") or "").strip()
    connected_peers_lower = {
        p.name.lower() for p in getattr(wroom, "peers", {}).values() if p.writer is not None
    }
    if not uname or uname.lower() not in connected_peers_lower:
        return False
    t0_conn = sum(
        1 for p in getattr(wroom, "peers", {}).values()
        if p.writer is not None and 0 <= p.sid < len(wroom.slots) and int(wroom.slots[p.sid].get("team", 0)) == 0
    )
    t1_conn = sum(
        1 for p in getattr(wroom, "peers", {}).values()
        if p.writer is not None and 0 <= p.sid < len(wroom.slots) and int(wroom.slots[p.sid].get("team", 0)) == 1
    )
    if wroom.winner_team is not None or t0_conn == 0 or t1_conn == 0:
        return False
    # If match is actively in progress (not LOBBY) and has run for at least 300 seconds (5 minutes) with other players still in the room
    in_progress = wroom.phase not in ("LOBBY", "FAILED") and not wroom.match_scored
    run_duration = (now - wroom.match_started_at) if wroom.match_started_at > 0 else 0.0
    init_cnt = int(getattr(wroom, "initial_player_count", 0) or len(wroom.peers))
    if 0 < init_cnt <= 4:
        return False
    mem_count = db.execute("SELECT count(*) FROM members WHERE room_id=?", (room_id,)).fetchone()[0]
    if in_progress and run_duration >= 300.0 and mem_count >= 2:
        pst = wroom.ensure_player_stat(uname)
        if not pst.get("abandoned"):
            pst["abandoned"] = True
            _penalize_match_abandon(db, user_dict["id"], uname, room_row["name"], user_dict.get("hwid", ""), wroom=wroom)
            db.execute(
                "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
                (
                    room_id,
                    user_dict["id"],
                    f"🚨 [LEAVER] «{uname}» (#{user_dict['uid_num']}) тоглолтыг дундаас нь хаяж гарлаа! (+1 Leave торгууль тооцогдлоо)",
                    now,
                ),
            )
            return True
    return False


def _score_w3gs_match(wroom):
    if wroom.match_scored:
        return
    wroom.match_scored = True
    now = time.time()
    summary_parts = []
    init_cnt = int(getattr(wroom, "initial_player_count", 0) or len(wroom.player_stats))
    t_counts = getattr(wroom, "initial_team_counts", None) or {}
    t0_cnt = int(t_counts.get(0, 0))
    t1_cnt = int(t_counts.get(1, 0))
    if t0_cnt == 0 and t1_cnt == 0:
        t0_cnt = sum(1 for st in wroom.player_stats.values() if int(st.get("team", 0)) == 0)
        t1_cnt = sum(1 for st in wroom.player_stats.values() if int(st.get("team", 0)) == 1)

    t0_kills = sum(int(st.get("kills", 0)) for st in wroom.player_stats.values() if int(st.get("team", 0)) == 0)
    t1_kills = sum(int(st.get("kills", 0)) for st in wroom.player_stats.values() if int(st.get("team", 0)) == 1)
    t0_assists = sum(int(st.get("assists", 0)) for st in wroom.player_stats.values() if int(st.get("team", 0)) == 0)
    t1_assists = sum(int(st.get("assists", 0)) for st in wroom.player_stats.values() if int(st.get("team", 0)) == 1)
    has_kda = (
        (t0_kills + t1_kills + t0_assists + t1_assists) > 0
        or any(int(st.get("deaths", 0)) > 0 for st in wroom.player_stats.values())
    )
    if not has_kda and wroom.winner_team is None:
        return

    if wroom.winner_team is not None:
        win_team = int(wroom.winner_team)
    elif t0_kills != t1_kills:
        win_team = 0 if t0_kills > t1_kills else 1
    elif getattr(wroom, "first_empty_team", None) in (0, 1):
        win_team = 1 - int(wroom.first_empty_team)
    elif t0_assists != t1_assists:
        win_team = 0 if t0_assists > t1_assists else 1
    else:
        win_team = 0

    init_players_low = {p.lower() for p in (getattr(wroom, "initial_players", None) or set())}
    is_5v5 = (init_cnt >= 10 and t0_cnt >= 5 and t1_cnt >= 5)
    is_ranked_5v5 = is_5v5 and (wroom.winner_team is not None or has_kda)

    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        for pname, st in list(wroom.player_stats.items()):
            k = int(st.get("kills", 0))
            d = int(st.get("deaths", 0))
            a = int(st.get("assists", 0))
            team = int(st.get("team", 0))
            if init_players_low and pname.lower() not in init_players_low and k == 0 and d == 0 and a == 0:
                continue
            u_row = db.execute("SELECT rowid AS rowid, * FROM users WHERE name=? COLLATE NOCASE", (pname,)).fetchone()
            if not u_row:
                continue
            cur_elo = int(u_row["elo"] or 1000)
            games = int(u_row["games_played"] or 0)
            wins = int(u_row["wins"] or 0)
            losses = int(u_row["losses"] or 0)
            tot_kills = int(u_row["kills"] or 0)
            tot_deaths = int(u_row["deaths"] or 0)
            tot_assists = int(u_row["assists"] or 0)
            leaves = int(u_row["leaves"] or 0)
            streak = int(u_row["clean_streak"] or 0)

            if st.get("abandoned"):
                if k > 0 or d > 0 or a > 0:
                    db.execute(
                        "UPDATE users SET kills=?, deaths=?, assists=? WHERE id=?",
                        (tot_kills + k, tot_deaths + d, tot_assists + a, u_row["id"]),
                    )
                continue

            won = (team == win_team)

            if not is_ranked_5v5:
                # Non-5v5 match: ELO is strictly only for full 5v5 matches
                continue

            streak += 1
            base_delta = 25 if won else -15
            perf_delta = (k * 3) + (a * 1) - max(0, (d - 3) * 1)
            raw_delta = base_delta + perf_delta

            # Carry protection: if a pro player gets 10+ kills and positive K/D on a losing team, never lose ELO
            if not won and k >= 10 and k > d:
                raw_delta = max(8, raw_delta)
            # Feeder damper: if 0 kills and 8+ deaths on winning team, cap gain
            if won and k == 0 and d >= 8:
                raw_delta = min(5, raw_delta)

            raw_delta = max(-45, min(60, raw_delta))
            new_games = games + 1
            new_wins = wins + (1 if won else 0)
            new_losses = losses + (0 if won else 1)

            # Redemption: 3 consecutive clean matches reduces leave count by 1
            if streak >= 3 and leaves > 0:
                leaves -= 1
                streak = 0

            if new_games < 10:
                new_elo = max(100, min(5000, cur_elo + raw_delta))
                hist_delta = 0
                hist_elo_after = 0
                summary_parts.append(f"{pname} ({k}/{d}/{a} • {'WIN' if won else 'LOSS'} • ⏳ {new_games}/10)")
            elif new_games == 10:
                new_elo = _placement_elo(new_wins, new_games, tot_kills + k, tot_deaths + d, leaves)
                hist_delta = new_elo - 1000
                hist_elo_after = new_elo
                summary_parts.append(f"{pname} ({k}/{d}/{a} • 🎖️ Түвшин тогтлоо: {new_elo} ELO)")
            else:
                new_elo = max(100, min(5000, cur_elo + raw_delta))
                hist_delta = new_elo - cur_elo
                hist_elo_after = new_elo
                sign = "+" if hist_delta >= 0 else ""
                summary_parts.append(f"{pname} ({k}/{d}/{a} • {sign}{hist_delta} ELO -> {new_elo})")

            db.execute(
                "UPDATE users SET elo=?, games_played=?, wins=?, losses=?, kills=?, deaths=?, assists=?, leaves=?, clean_streak=? WHERE id=?",
                (new_elo, new_games, new_wins, new_losses, tot_kills + k, tot_deaths + d, tot_assists + a, leaves, streak, u_row["id"]),
            )
            _record_match_history(db, u_row["id"], wroom, "WIN" if won else "LOSS", k, d, a, team, hist_delta, hist_elo_after, now)

        if summary_parts and db.execute("SELECT 1 FROM rooms WHERE id=?", (wroom.room_id,)).fetchone():
            owner_row = db.execute("SELECT owner FROM rooms WHERE id=?", (wroom.room_id,)).fetchone()
            if owner_row:
                db.execute(
                    "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
                    (wroom.room_id, owner_row["owner"], "🏆 Тоглолт дууслаа! ELO & Kill үнэлгээ: " + " | ".join(summary_parts), now),
                )


def password_hash(password, salt):
    if not password_slots.acquire(blocking=False):
        raise HTTPException(503, "Authentication busy; retry shortly")
    try:
        return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                              n=16384, r=8, p=1, dklen=32).hex()
    finally:
        password_slots.release()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(authorization: str = Header(default=""), x_mr_hwid: str = Header(default="")):
    if not authorization.startswith("Bearer ") or len(authorization) > 256:
        raise HTTPException(401, "Sign in required")
    now = time.time()
    clean_hwid = (x_mr_hwid or "").strip()[:128]
    with database() as db:
        row = db.execute(
            "SELECT u.rowid AS rowid, u.* FROM users u "
            "JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires>?",
            (digest(authorization[7:]), now),
        ).fetchone()
        if row:
            if (now - float(row["last_seen"] or 0)) > 15.0 or (clean_hwid and row["hwid"] != clean_hwid):
                if clean_hwid:
                    db.execute("UPDATE users SET last_seen=?, hwid=? WHERE id=?", (now, clean_hwid, row["id"]))
                else:
                    db.execute("UPDATE users SET last_seen=? WHERE id=?", (now, row["id"]))
    if not row:
        raise HTTPException(401, "Session expired or invalid")
    d = dict(row)
    d["uid_num"] = 10000 + int(row["rowid"])
    if clean_hwid:
        d["hwid"] = clean_hwid
    return d


def _resolve_target_user(db, target_str: str):
    clean = (target_str or "").strip()
    if not clean:
        return None
    if clean.startswith("#"):
        clean_num = clean[1:].strip()
    else:
        clean_num = clean
    if clean_num.isdigit():
        num_val = int(clean_num)
        rowid_val = num_val - 10000 if num_val > 10000 else num_val
        row = db.execute("SELECT rowid AS rowid, * FROM users WHERE rowid=?", (rowid_val,)).fetchone()
        if row:
            return row
    return db.execute("SELECT rowid AS rowid, * FROM users WHERE name=? COLLATE NOCASE", (clean,)).fetchone()


def current_admin(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer ") or len(authorization) > 256:
        raise HTTPException(401, "Admin sign in required")
    with database() as db:
        db.execute("DELETE FROM admin_sessions WHERE expires<?", (time.time(),))
        row = db.execute(
            "SELECT username FROM admin_sessions WHERE token_hash=? AND expires>?",
            (digest(authorization[7:]), time.time()),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Admin session expired or invalid")
    return {"username": row["username"]}


_last_session_cleanup_ts = 0.0


def cleanup(db):
    global _last_session_cleanup_ts
    now = time.time()
    for rid, wroom in list(w3gs_manager.rooms.items()):
        if wroom.phase != "LOBBY" and (now - wroom.updated_at) < 600:
            db.execute("UPDATE rooms SET updated=? WHERE id=? AND updated>? AND updated<?", (now, rid, now - ROOM_SECONDS, now - 15.0))
    expired = [r[0] for r in db.execute("SELECT id FROM rooms WHERE updated<?", (now - ROOM_SECONDS,)).fetchall()]
    if expired:
        for rid in expired:
            w3gs_manager.remove_room(rid)
        db.execute("DELETE FROM rooms WHERE updated<?", (now - ROOM_SECONDS,))
    if now - _last_session_cleanup_ts >= 15.0:
        _last_session_cleanup_ts = now
        db.execute("DELETE FROM sessions WHERE expires<?", (now,))
        db.execute("DELETE FROM room_invites WHERE created<?", (now - 300,))


def require_member(db, room_id, user):
    cleanup(db)
    if not db.execute("SELECT 1 FROM members WHERE room_id=? AND user_id=?", (room_id, user["id"])).fetchone():
        raise HTTPException(403, "Join this room first")


def resolve_map_meta(db, map_query: str) -> dict:
    clean_q = map_query.strip()
    base_q = Path(clean_q.replace("\\", "/")).name
    row = db.execute(
        "SELECT * FROM maps WHERE id=? OR filename=? OR title=? OR map_path=? ORDER BY is_default DESC LIMIT 1",
        (clean_q, base_q, clean_q, clean_q),
    ).fetchone()
    if not row:
        row = db.execute("SELECT * FROM maps ORDER BY is_default DESC, created ASC LIMIT 1").fetchone()
    if row:
        meta = json.loads(row["meta_json"])
        meta["id"] = row["id"]
        return meta
    return _default_lod_meta()


def _on_w3gs_chat_announce(rid: str, msg_text: str):
    now = time.time()
    try:
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            room = db.execute("SELECT owner FROM rooms WHERE id=?", (rid,)).fetchone()
            if room:
                recent = db.execute(
                    "SELECT id, text FROM messages WHERE room_id=? AND created>? ORDER BY id DESC LIMIT 1",
                    (rid, now - 2.0),
                ).fetchone()
                if recent and (recent["text"] == msg_text or msg_text.startswith(recent["text"][:40])):
                    return
                db.execute(
                    "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
                    (rid, room["owner"], msg_text, now),
                )
    except Exception:
        pass


def _on_w3gs_player_dropped(wroom, dropped_name: str):
    now = time.time()
    try:
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            room = db.execute("SELECT * FROM rooms WHERE id=?", (wroom.room_id,)).fetchone()
            if not room:
                return
            u_row = db.execute("SELECT rowid AS rowid, * FROM users WHERE name=? COLLATE NOCASE", (dropped_name,)).fetchone()
            if u_row:
                is_quit = getattr(wroom, "last_drop_reason", "drop") == "quit"
                run_duration = (now - wroom.match_started_at) if wroom.match_started_at > 0 else 0.0
                if not is_quit or run_duration >= 90.0:
                    _penalize_match_abandon(db, u_row["id"], u_row["name"], room["name"], u_row["hwid"] or "", wroom=wroom)
                db.execute("DELETE FROM members WHERE room_id=? AND user_id=?", (wroom.room_id, u_row["id"]))
                if room["owner"] == u_row["id"]:
                    # Host left the match: hand the room to another remaining member (rooms.owner is UNIQUE).
                    heir = db.execute(
                        "SELECT u.id, u.name FROM members m JOIN users u ON u.id=m.user_id "
                        "WHERE m.room_id=? AND u.id NOT IN (SELECT owner FROM rooms) LIMIT 1",
                        (wroom.room_id,),
                    ).fetchone()
                    if heir:
                        db.execute("UPDATE rooms SET owner=? WHERE id=?", (heir["id"], wroom.room_id))
                        wroom.owner_name = heir["name"]
                        room = db.execute("SELECT * FROM rooms WHERE id=?", (wroom.room_id,)).fetchone()
                    else:
                        db.execute("DELETE FROM rooms WHERE id=?", (wroom.room_id,))
                        return
                kicked_list = json.loads(room["kicked_json"] if "kicked_json" in room.keys() and room["kicked_json"] else "[]")
                if u_row["id"] not in kicked_list:
                    kicked_list.append(u_row["id"])
                if u_row["name"] not in kicked_list:
                    kicked_list.append(u_row["name"])
                if wroom.phase == "LOBBY":
                    db.execute("UPDATE rooms SET kicked_json=?, launch_signal=0, updated=? WHERE id=?", (json.dumps(kicked_list), now, wroom.room_id))
                else:
                    db.execute("UPDATE rooms SET kicked_json=?, updated=? WHERE id=?", (json.dumps(kicked_list), now, wroom.room_id))
                db.execute(
                    "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
                    (
                        wroom.room_id,
                        room["owner"],
                        (
                            f"🚪 «{dropped_name}» (#{10000 + int(u_row['rowid'])}) тоглолтоос өөрөө гарсан (Quit Mission) тул буцаж орох (Rejoin) эрхгүй."
                            if is_quit
                            else f"👢 Хүлээх хугацаа (3 мин) дууссан тул Host «{dropped_name}» (#{10000 + int(u_row['rowid'])})-ийг тоглолтоос хаслаа (Drop • +1 Leave)."
                        ),
                        now,
                    ),
                )
            elif wroom.phase == "LOBBY":
                db.execute("UPDATE rooms SET launch_signal=0, updated=? WHERE id=?", (now, wroom.room_id))
    except Exception:
        pass


def _on_w3gs_room_remake(wroom, reason_msg: str):
    now = time.time()
    try:
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            room = db.execute("SELECT * FROM rooms WHERE id=?", (wroom.room_id,)).fetchone()
            if room:
                db.execute("UPDATE rooms SET launch_signal=0, updated=? WHERE id=?", (now, wroom.room_id))
                db.execute(
                    "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
                    (wroom.room_id, room["owner"], f"{reason_msg} (LAN дотор өрөө шинээр бэлэн боллоо!)", now),
                )
    except Exception:
        pass


def ensure_w3gs_room(rid: str, room_row, host_name: str = "Host", db=None):
    wroom = w3gs_manager.get_room(rid)
    if wroom is None:
        map_meta = resolve_map_meta(db, room_row["map_name"]) if db is not None else None
        wroom = w3gs_manager.create_room(rid, room_row["name"], host_name, map_meta=map_meta)
    if host_name and host_name != "Host":
        wroom.owner_name = host_name
    wroom.on_match_complete_cb = _score_w3gs_match
    wroom.on_player_dropped_cb = _on_w3gs_player_dropped
    wroom.on_chat_announce_cb = _on_w3gs_chat_announce
    wroom.on_room_remake_cb = _on_w3gs_room_remake
    return wroom


def _find_map_file(filename: str) -> Path | None:
    p1 = get_maps_dir() / Path(filename).name
    if p1.is_file():
        return p1
    p2 = Path(__file__).resolve().parent.parent / "WAR3_HUULAH_FILES" / "Maps" / "Download" / Path(filename).name
    if p2.is_file():
        return p2
    return None


def _format_map_row(row) -> dict:
    meta = json.loads(row["meta_json"])
    crc_bytes = bytes(meta.get("map_crc", [0, 0, 0, 0]))
    sha1_bytes = bytes(meta.get("map_sha1", [0] * 20))
    f_path = _find_map_file(row["filename"])
    return {
        "id": row["id"],
        "filename": row["filename"],
        "title": row["title"],
        "map_path": row["map_path"],
        "file_size": row["file_size"],
        "sha256": row["sha256"],
        "crc_hex": crc_bytes.hex(),
        "sha1_hex": sha1_bytes.hex(),
        "num_players": meta.get("num_players", 10),
        "has_cam": bool(row["has_cam"]),
        "has_reconnect": bool(row["has_reconnect"]),
        "is_default": bool(row["is_default"]),
        "download_available": f_path is not None,
        "download_url": f"/api/maps/{row['id']}/download",
        "created": row["created"],
    }


def _find_download_file(filename: str) -> Path | None:
    if not filename:
        return None
    p = get_downloads_dir() / Path(filename).name
    if p.is_file():
        return p
    return None


def _format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes} B"


def _format_download_row(row) -> dict:
    ext_url = (row["external_url"] or "").strip()
    is_r2 = ext_url.startswith("r2://")
    local_f = _find_download_file(row["filename"])
    is_external = bool(ext_url) and not is_r2
    ready = is_r2 or is_external or (local_f is not None)
    size_lbl = row["size_label"]
    if not ext_url and local_f is not None:
        size_lbl = _format_size(local_f.stat().st_size)
    download_url = ext_url if is_external else f"/api/downloads/{row['slot']}/file"
    return {
        "slot": row["slot"],
        "title": row["title"],
        "platform": row["platform"],
        "version": row["version"],
        "description": row["description"],
        "filename": row["filename"],
        "external_url": ext_url,
        "size_label": size_lbl or "Бэлэн",
        "button_text": row["button_text"] or "Татах",
        "is_external": is_external,
        "is_r2": is_r2,
        "ready": ready,
        "download_url": download_url,
        "updated": row["updated"],
    }


@app.get("/", response_class=HTMLResponse)
def home_page():
    return HTMLResponse(PUBLIC_HTML)


@app.get("/api/public/overview")
def public_overview():
    with database() as db:
        cleanup(db)
        dl_rows = db.execute("SELECT * FROM downloads ORDER BY slot ASC").fetchall()
        map_rows = db.execute("SELECT * FROM maps ORDER BY is_default DESC, title ASC").fetchall()
        room_rows = db.execute(
            "SELECT r.id,r.name,r.map_name,r.capacity,r.room_code,u.name AS host,"
            "(SELECT count(*) FROM members m WHERE m.room_id=r.id) AS players "
            "FROM rooms r JOIN users u ON u.id=r.owner ORDER BY r.rowid DESC LIMIT 50"
        ).fetchall()

    slot_order = {"client_win": 0, "game_full": 1}
    dls = sorted(
        [_format_download_row(r) for r in dl_rows if r["slot"] != "client_mac"],
        key=lambda x: slot_order.get(x["slot"], 99),
    )
    rooms_out = []
    for r in room_rows:
        item = dict(r)
        rc = (item.pop("room_code", "") or "").strip()
        item["is_locked"] = 1 if rc else 0
        wroom = w3gs_manager.get_room(item["id"])
        item["phase"] = wroom.phase if wroom else "LOBBY"
        if wroom and wroom.phase != "LOBBY" and wroom.peers:
            item["players"] = len(wroom.peers)
        rooms_out.append(item)
    rooms_out.sort(key=lambda x: (0 if x.get("phase", "LOBBY") == "LOBBY" else 1, int(x.get("is_locked", 0))))

    return {
        "status": "ok",
        "version": "0.4.0",
        "w3gs_port": w3gs_manager.listen_port,
        "active_rooms": len(rooms_out),
        "downloads": dls,
        "maps": [_format_map_row(m) for m in map_rows],
        "rooms": rooms_out,
    }


@app.get("/assets/mongolranger_v48_ui_preview.png")
def serve_v48_ui_preview():
    p = Path(__file__).resolve().parent / "assets" / "mongolranger_v48_ui_preview.png"
    if not p.is_file():
        raise HTTPException(404, "Preview image not found")
    return FileResponse(
        path=str(p),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/updates/ZevArena-Setup.exe")
@app.get("/updates/MongolRanger_4.8_x64-setup.exe")
def download_nsis_setup_exe():
    nsis_path = _find_download_file("ZevArena-Setup.exe") or _find_download_file("MongolRanger_4.8_x64-setup.exe")
    if nsis_path is None or not nsis_path.is_file():
        raise HTTPException(404, "ZevArena-Setup.exe not found")
    return FileResponse(
        path=str(nsis_path),
        media_type="application/x-msdownload",
        filename="ZevArena-Setup.exe",
    )


@app.get("/api/downloads/{slot}/file")
def download_slot_file(slot: str, request: Request):
    with database() as db:
        row = db.execute("SELECT * FROM downloads WHERE slot=?", (slot,)).fetchone()
    if not row:
        raise HTTPException(404, "Татах файл олдсонгүй")
    ext_url = (row["external_url"] or "").strip()
    if ext_url.startswith("r2://"):
        r2_key = ext_url[5:]
        dl_name = row["filename"] or Path(r2_key).name
        signed_url = presign_r2_url("GET", r2_key, expires_sec=21600, download_filename=dl_name)
        return RedirectResponse(url=signed_url, status_code=302)
    if ext_url:
        return RedirectResponse(url=ext_url, status_code=302)
    f_path = _find_download_file(row["filename"])
    if f_path is None:
        raise HTTPException(404, "Татах файл сервер дээр хараахан ороогүй байна")
    return FileResponse(
        path=str(f_path),
        media_type="application/octet-stream",
        filename=row["filename"],
    )


@app.get("/healthz")
def health():
    with database() as db:
        db.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        maps_count = db.execute("SELECT count(*) FROM maps").fetchone()[0]
    return {
        "status": "ok",
        "service": "mongolranger",
        "version": "0.4.0",
        "w3gs_port": w3gs_manager.listen_port,
        "active_rooms": len(w3gs_manager.rooms),
        "maps_count": maps_count,
    }


# ---------------------------------------------------------------------------
# PUBLIC / CLIENT MAP CATALOG & FAST HTTPS DOWNLOAD ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/api/maps")
def list_maps():
    with database() as db:
        rows = db.execute("SELECT * FROM maps ORDER BY is_default DESC, title ASC").fetchall()
    return {"maps": [_format_map_row(r) for r in rows]}


@app.get("/api/maps/{map_id}/download")
def download_map(map_id: str):
    with database() as db:
        row = db.execute("SELECT * FROM maps WHERE id=? OR filename=?", (map_id, map_id)).fetchone()
    if not row:
        raise HTTPException(404, "Map not found in catalog")
    f_path = _find_map_file(row["filename"])
    if f_path is None:
        raise HTTPException(404, "Map binary file not uploaded to server disk yet")
    return FileResponse(
        path=str(f_path),
        media_type="application/octet-stream",
        filename=row["filename"],
    )


PATCH_GAME_DLL_SHA256 = "175e9ba8460ab709ed2ef8adb02919876b4e0d4762903016b18bfb0b61b2351b"
PATCH_GAME_DLL_SIZE = 12042240


@app.get("/api/patch/info")
def patch_info():
    return {
        "ok": True,
        "game_dll_sha256": PATCH_GAME_DLL_SHA256,
        "game_dll_size": PATCH_GAME_DLL_SIZE,
        "download_url": "/api/patch/game-dll",
        "features": [
            "MongolRanger Reconnect & View-Restore Game.dll (1.26a)",
            "MongolRanger Anti-MapHack Shield (Process/DLL/Memory/W3GS Guard)",
            "4GB Large Address Aware (LAA) Crash Protection",
            "Windows 7/10/11 Compatibility & Black-Screen Fix",
            "Automatic Official Map Sync (Maps\\Download)",
        ],
    }


@app.get("/api/patch/game-dll")
def download_patch_game_dll():
    local_dll = _find_download_file("Game.dll")
    if local_dll is not None and local_dll.is_file():
        return FileResponse(
            path=str(local_dll),
            media_type="application/octet-stream",
            filename="Game.dll",
        )
    signed_url = presign_r2_url("GET", "patch/Game.dll", expires_sec=21600, download_filename="Game.dll")
    return RedirectResponse(url=signed_url, status_code=302)


_CLIENT_EXE_HASH_CACHE: dict[str, object] = {"mtime_ns": 0, "size": 0, "sha256": ""}


@app.get("/api/client/version")
def client_version_info():
    f_path = _find_download_file("MongolRanger-Setup.exe")
    sha256_hex = ""
    size_bytes = 0
    if f_path is not None and f_path.is_file():
        st = f_path.stat()
        size_bytes = st.st_size
        if _CLIENT_EXE_HASH_CACHE["mtime_ns"] == st.st_mtime_ns and _CLIENT_EXE_HASH_CACHE["size"] == size_bytes and _CLIENT_EXE_HASH_CACHE["sha256"]:
            sha256_hex = str(_CLIENT_EXE_HASH_CACHE["sha256"])
        else:
            raw = f_path.read_bytes()
            sha256_hex = hashlib.sha256(raw).hexdigest()
            size_bytes = len(raw)
            _CLIENT_EXE_HASH_CACHE["mtime_ns"] = st.st_mtime_ns
            _CLIENT_EXE_HASH_CACHE["size"] = size_bytes
            _CLIENT_EXE_HASH_CACHE["sha256"] = sha256_hex
    return {
        "ok": True,
        "version": "v4.8",
        "filename": "MongolRanger-Setup.exe",
        "sha256": sha256_hex,
        "size_bytes": size_bytes,
        "download_url": "/api/client/exe",
    }


@app.get("/api/client/exe")
def download_client_exe():
    f_path = _find_download_file("MongolRanger-Setup.exe")
    if f_path is None or not f_path.is_file():
        raise HTTPException(404, "MongolRanger-Setup.exe not found")
    return FileResponse(
        path=str(f_path),
        media_type="application/octet-stream",
        filename="MongolRanger-Setup.exe",
    )


@app.get("/install")
def powershell_quick_install():
    ps_script = r"""$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::ServerCertificateValidationCallback = {$true} } catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]3072 -bor [Net.SecurityProtocolType]::Tls } catch {}
$dir = Join-Path $env:LOCALAPPDATA 'MongolRanger'
if (!(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
try {
    $r64 = (Get-ItemProperty -Path 'HKLM:\Software\Microsoft\.NETFramework' -Name 'InstallRoot' -ErrorAction SilentlyContinue).InstallRoot
    $r32 = (Get-ItemProperty -Path 'HKLM:\Software\WOW6432Node\Microsoft\.NETFramework' -Name 'InstallRoot' -ErrorAction SilentlyContinue).InstallRoot
    if ([string]::IsNullOrWhiteSpace($r64) -or ([Environment]::Is64BitOperatingSystem -and [string]::IsNullOrWhiteSpace($r32))) {
        $fixCmd = "New-Item -Path 'HKLM:\Software\Microsoft\.NETFramework\Policy\v4.0' -Force | Out-Null; Set-ItemProperty -Path 'HKLM:\Software\Microsoft\.NETFramework' -Name 'InstallRoot' -Value '$env:WINDIR\Microsoft.NET\Framework64\'; Set-ItemProperty -Path 'HKLM:\Software\Microsoft\.NETFramework\Policy\v4.0' -Name '30319' -Value '30319-30319'; New-Item -Path 'HKLM:\Software\WOW6432Node\Microsoft\.NETFramework\Policy\v4.0' -Force | Out-Null; Set-ItemProperty -Path 'HKLM:\Software\WOW6432Node\Microsoft\.NETFramework' -Name 'InstallRoot' -Value '$env:WINDIR\Microsoft.NET\Framework\'; Set-ItemProperty -Path 'HKLM:\Software\WOW6432Node\Microsoft\.NETFramework\Policy\v4.0' -Name '30319' -Value '30319-30319'"
        Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -Wait -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command `"$fixCmd`""
    }
} catch {}
$exe = Join-Path $dir 'MongolRanger.exe'
$cfg = Join-Path $dir 'MongolRanger.exe.config'
Get-Process -Name 'MongolRanger*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 300
$wc = New-Object System.Net.WebClient
try {
    $wc.DownloadFile('https://zevarena.com/api/client/exe', $exe)
} catch {
    $wc.DownloadFile('http://103.153.141.135/api/client/exe', $exe)
}
$cfgXml = '<?xml version="1.0" encoding="utf-8" ?><configuration><startup useLegacyV2RuntimeActivationPolicy="true"><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.0"/><supportedRuntime version="v4.0"/><supportedRuntime version="v2.0.50727"/></startup></configuration>'
[IO.File]::WriteAllText($cfg, $cfgXml, [Text.Encoding]::UTF8)
try { Remove-Item -Path ($exe + ':Zone.Identifier') -Force -ErrorAction SilentlyContinue } catch {}
try {
    $wsh = New-Object -ComObject WScript.Shell
    $desk = [Environment]::GetFolderPath('Desktop')
    $lnk = $wsh.CreateShortcut((Join-Path $desk 'ZevArena.lnk'))
    $lnk.TargetPath = $exe
    $lnk.WorkingDirectory = $dir
    $lnk.Description = 'ZevArena — Warcraft III 1.26a Online Platform'
    $lnk.IconLocation = "$exe,0"
    $lnk.Save()
} catch {}
Start-Process -FilePath $exe -WorkingDirectory $dir
"""
    return Response(content=ps_script, media_type="text/plain; charset=utf-8")




# ---------------------------------------------------------------------------
# WEB ADMIN DASHBOARD (/admin) & ADMIN MANAGEMENT API
# ---------------------------------------------------------------------------

@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/", response_class=HTMLResponse)
def admin_page():
    return HTMLResponse(ADMIN_HTML)


@app.post("/api/admin/login")
def admin_login(data: AdminLoginInput):
    if data.username.lower() != ADMIN_USER.lower():
        raise HTTPException(401, "Админ нэвтрэх нэр эсвэл нууц үг буруу байна")
    with database() as db:
        pw_row = db.execute("SELECT value FROM admin_settings WHERE key='admin_pw'").fetchone()
    if pw_row:
        salt_hex, stored_hash = pw_row["value"].split(":", 1)
        cand = password_hash(data.password, salt_hex)
        ok = hmac.compare_digest(cand, stored_hash)
    else:
        ok = hmac.compare_digest(data.password, ADMIN_DEFAULT_PASS)
    if not ok:
        raise HTTPException(401, "Админ нэвтрэх нэр эсвэл нууц үг буруу байна")
    token = secrets.token_urlsafe(32)
    with database() as db:
        db.execute("DELETE FROM admin_sessions WHERE expires<?", (time.time(),))
        db.execute(
            "INSERT INTO admin_sessions VALUES(?,?,?)",
            (digest(token), ADMIN_USER, time.time() + SESSION_SECONDS),
        )
    return {"token": token, "username": ADMIN_USER}


@app.post("/api/admin/password")
def admin_change_password(data: AdminPasswordInput, admin=Depends(current_admin)):
    salt = secrets.token_hex(16)
    hashed = password_hash(data.password, salt)
    with database() as db:
        db.execute(
            "INSERT OR REPLACE INTO admin_settings(key,value) VALUES('admin_pw',?)",
            (f"{salt}:{hashed}",),
        )
    return {"ok": True}


@app.get("/api/admin/overview")
def admin_overview(admin=Depends(current_admin)):
    with database() as db:
        cleanup(db)
        dl_rows = db.execute("SELECT * FROM downloads ORDER BY slot ASC").fetchall()
        map_rows = db.execute("SELECT * FROM maps ORDER BY is_default DESC, title ASC").fetchall()
        room_rows = db.execute(
            "SELECT r.id,r.name,r.map_name,r.capacity,r.room_code,u.name AS host,"
            "(SELECT count(*) FROM members m WHERE m.room_id=r.id) AS players "
            "FROM rooms r JOIN users u ON u.id=r.owner ORDER BY r.rowid DESC"
        ).fetchall()
        user_rows = db.execute(
            "SELECT u.id,u.name,u.created,r.name AS room_name "
            "FROM users u LEFT JOIN members m ON m.user_id=u.id "
            "LEFT JOIN rooms r ON r.id=m.room_id ORDER BY u.created DESC LIMIT 500"
        ).fetchall()

    slot_order = {"client_win": 0, "game_full": 1}
    dls = sorted(
        [_format_download_row(r) for r in dl_rows if r["slot"] != "client_mac"],
        key=lambda x: slot_order.get(x["slot"], 99),
    )

    rooms_out = []
    for r in room_rows:
        item = dict(r)
        rc = (item.pop("room_code", "") or "").strip()
        item["is_locked"] = 1 if rc else 0
        wroom = w3gs_manager.get_room(item["id"])
        item["phase"] = wroom.phase if wroom else "LOBBY"
        if wroom and wroom.phase != "LOBBY" and wroom.peers:
            item["players"] = len(wroom.peers)
        item["w3gs_players"] = (
            [
                {"name": p.name, "pid": p.pid, "connected": p.writer is not None, "loaded": p.loaded}
                for p in wroom.peers.values()
            ]
            if wroom
            else []
        )
        rooms_out.append(item)
    rooms_out.sort(key=lambda x: (0 if x.get("phase", "LOBBY") == "LOBBY" else 1, int(x.get("is_locked", 0))))

    return {
        "version": "0.4.0",
        "w3gs_port": w3gs_manager.listen_port,
        "r2_enabled": is_r2_configured(),
        "downloads": dls,
        "maps": [_format_map_row(m) for m in map_rows],
        "rooms": rooms_out,
        "users": [dict(u) for u in user_rows],
    }


@app.post("/api/admin/downloads/{slot}/r2-presign")
def admin_r2_presign_download(
    slot: str,
    data: R2PresignInput,
    admin=Depends(current_admin),
):
    if not is_r2_configured():
        raise HTTPException(503, "Cloudflare R2 тохиргоо олдсонгүй")
    clean_fname = re.sub(r"[^A-Za-z0-9_.\- ()]", "_", Path(data.filename).name).strip()
    if not clean_fname:
        raise HTTPException(400, "Файлын нэр буруу байна")
    with database() as db:
        row = db.execute("SELECT * FROM downloads WHERE slot=?", (slot,)).fetchone()
        if not row:
            raise HTTPException(404, "Download slot олдсонгүй")
    r2_key = normalize_r2_key(f"downloads/{clean_fname}")
    upload_url = presign_r2_url("PUT", r2_key, expires_sec=7200)
    return {
        "ok": True,
        "slot": slot,
        "filename": clean_fname,
        "r2_key": r2_key,
        "upload_url": upload_url,
    }


@app.post("/api/admin/downloads/{slot}/r2-complete")
def admin_r2_complete_download(
    slot: str,
    data: R2CompleteInput,
    admin=Depends(current_admin),
):
    r2_key = normalize_r2_key(data.r2_key)
    clean_fname = re.sub(r"[^A-Za-z0-9_.\- ()]", "_", Path(data.filename).name).strip() or Path(r2_key).name
    with database() as db:
        row = db.execute("SELECT * FROM downloads WHERE slot=?", (slot,)).fetchone()
        if not row:
            raise HTTPException(404, "Download slot олдсонгүй")
        new_ver = data.version.strip() or row["version"]
        size_lbl = f"{_format_size(data.size_bytes)} (Cloudflare R2)" if data.size_bytes > 0 else "Cloudflare R2 CDN"
        db.execute(
            "UPDATE downloads SET filename=?, external_url=?, version=?, size_label=?, updated=? WHERE slot=?",
            (clean_fname, f"r2://{r2_key}", new_ver, size_lbl, time.time(), slot),
        )
        updated_row = db.execute("SELECT * FROM downloads WHERE slot=?", (slot,)).fetchone()
    return {"ok": True, "download": _format_download_row(updated_row)}


@app.post("/api/admin/downloads/{slot}/upload")
async def admin_upload_download(
    slot: str,
    request: Request,
    filename: str = "package.zip",
    version: str = "",
    storage: str = "local",
    admin=Depends(current_admin),
):
    clean_fname = re.sub(r"[^A-Za-z0-9_.\- ()]", "_", Path(filename).name).strip()
    if not clean_fname:
        raise HTTPException(400, "Файлын нэр буруу байна")
    body = await request.body()
    if len(body) < 16:
        raise HTTPException(400, "Файл хоосон байна")
    with database() as db:
        row = db.execute("SELECT * FROM downloads WHERE slot=?", (slot,)).fetchone()
        if not row:
            raise HTTPException(404, "Download slot олдсонгүй")
        new_ver = version.strip() or row["version"]
        if storage == "r2":
            r2_uri = upload_bytes_to_r2(f"downloads/{clean_fname}", body)
            size_lbl = f"{_format_size(len(body))} (Cloudflare R2)"
            db.execute(
                "UPDATE downloads SET filename=?, external_url=?, version=?, size_label=?, updated=? WHERE slot=?",
                (clean_fname, r2_uri, new_ver, size_lbl, time.time(), slot),
            )
        else:
            dest = get_downloads_dir() / clean_fname
            dest.write_bytes(body)
            size_lbl = _format_size(len(body))
            db.execute(
                "UPDATE downloads SET filename=?, external_url='', version=?, size_label=?, updated=? WHERE slot=?",
                (clean_fname, new_ver, size_lbl, time.time(), slot),
            )
        updated_row = db.execute("SELECT * FROM downloads WHERE slot=?", (slot,)).fetchone()
    return {"ok": True, "download": _format_download_row(updated_row)}


@app.post("/api/admin/downloads/{slot}/link")
def admin_save_download_link(
    slot: str,
    data: DownloadLinkInput,
    admin=Depends(current_admin),
):
    ext_url = data.external_url.strip()
    if ext_url and not ext_url.startswith(("http://", "https://", "r2://")):
        raise HTTPException(400, "Гадны линк http://, https:// эсвэл r2://-ээр эхлэх ёстой")
    with database() as db:
        row = db.execute("SELECT * FROM downloads WHERE slot=?", (slot,)).fetchone()
        if not row:
            raise HTTPException(404, "Download slot олдсонгүй")
        new_ver = data.version.strip() or row["version"]
        new_size = data.size_label.strip() or row["size_label"]
        new_btn = data.button_text.strip() or row["button_text"]
        db.execute(
            "UPDATE downloads SET external_url=?, version=?, size_label=?, button_text=?, updated=? WHERE slot=?",
            (ext_url, new_ver, new_size, new_btn, time.time(), slot),
        )
        updated_row = db.execute("SELECT * FROM downloads WHERE slot=?", (slot,)).fetchone()
    return {"ok": True, "download": _format_download_row(updated_row)}


@app.post("/api/admin/maps", status_code=201)
async def admin_upload_map(
    request: Request,
    filename: str = "map.w3x",
    title: str = "",
    enable_cam: int = 1,
    enable_reconnect: int = 1,
    is_default: int = 0,
    admin=Depends(current_admin),
):
    clean_fname = re.sub(r"[^A-Za-z0-9_.\- ()]", "_", Path(filename).name).strip()
    if not clean_fname.lower().endswith((".w3x", ".w3m")):
        raise HTTPException(400, "Зөвхөн .w3x эсвэл .w3m өргөтгөлтэй Warcraft III map оруулна уу")
    body = await request.body()
    if len(body) < 544:
        raise HTTPException(400, "Map файл хэт жижиг эсвэл хоосон байна")
    try:
        patched_bytes, meta = process_map_bytes(
            body,
            clean_fname,
            enable_cam=bool(enable_cam),
            enable_reconnect=bool(enable_reconnect),
        )
    except Exception as exc:
        raise HTTPException(400, f"Map боловсруулахад алдаа гарлаа: {exc}")

    if title.strip():
        meta["title"] = title.strip()

    dest_path = get_maps_dir() / clean_fname
    dest_path.write_bytes(patched_bytes)

    map_id = re.sub(r"[^a-z0-9_]+", "_", Path(clean_fname).stem.lower()).strip("_") or secrets.token_hex(6)
    with database() as db:
        existing = db.execute("SELECT id FROM maps WHERE filename=?", (clean_fname,)).fetchone()
        if existing:
            map_id = existing["id"]
        if is_default:
            db.execute("UPDATE maps SET is_default=0")
        db.execute(
            "INSERT OR REPLACE INTO maps VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                map_id,
                clean_fname,
                meta["title"],
                meta["map_path"],
                meta["file_size"],
                meta["sha256"],
                json.dumps(meta),
                1 if meta["has_cam"] else 0,
                1 if meta["has_reconnect"] else 0,
                1 if is_default else 0,
                time.time(),
            ),
        )
        row = db.execute("SELECT * FROM maps WHERE id=?", (map_id,)).fetchone()

    return {"ok": True, "map": _format_map_row(row)}


@app.post("/api/admin/maps/{map_id}/default")
def admin_set_default_map(map_id: str, admin=Depends(current_admin)):
    with database() as db:
        row = db.execute("SELECT id FROM maps WHERE id=?", (map_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Map олдсонгүй")
        db.execute("UPDATE maps SET is_default=0")
        db.execute("UPDATE maps SET is_default=1 WHERE id=?", (map_id,))
    return {"ok": True}


@app.delete("/api/admin/maps/{map_id}")
def admin_delete_map(map_id: str, admin=Depends(current_admin)):
    with database() as db:
        row = db.execute("SELECT * FROM maps WHERE id=?", (map_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Map олдсонгүй")
        db.execute("DELETE FROM maps WHERE id=?", (map_id,))
    f_path = get_maps_dir() / row["filename"]
    if f_path.is_file():
        try:
            f_path.unlink()
        except OSError:
            pass
    return {"ok": True}


@app.delete("/api/admin/rooms/{rid}")
def admin_close_room(rid: str, admin=Depends(current_admin)):
    with database() as db:
        db.execute("DELETE FROM rooms WHERE id=?", (rid,))
    w3gs_manager.remove_room(rid)
    return {"ok": True}


@app.delete("/api/admin/users/{uid}")
def admin_delete_user(uid: str, admin=Depends(current_admin)):
    with database() as db:
        owned = [r[0] for r in db.execute("SELECT id FROM rooms WHERE owner=?", (uid,)).fetchall()]
        for rid in owned:
            w3gs_manager.remove_room(rid)
        db.execute("DELETE FROM rooms WHERE owner=?", (uid,))
        db.execute("DELETE FROM members WHERE user_id=?", (uid,))
        db.execute("DELETE FROM users WHERE id=?", (uid,))
    return {"ok": True}


# ---------------------------------------------------------------------------
# PLAYER AUTH & ROOM / W3GS COORDINATOR API
# ---------------------------------------------------------------------------

def _check_hwid_new_account_allowed(db, hwid: str, now: float):
    clean_hwid = (hwid or "").strip()[:128]
    if not clean_hwid:
        return
    h_row = db.execute("SELECT * FROM hwid_registry WHERE hwid=?", (clean_hwid,)).fetchone()
    if not h_row:
        return
    # 1. If this specific computer abandoned a match in the last 25 minutes, block creating a throwaway account!
    abandon_elapsed = now - float(h_row["last_abandon_ts"] or 0.0)
    if abandon_elapsed < 1500.0:
        mins_left = max(1, int((1500.0 - abandon_elapsed) / 60) + 1)
        prev_u = h_row["last_abandon_user"] or "өмнөх хаяг"
        prev_r = h_row["last_abandon_room"] or "өмнөх өрөө"
        raise HTTPException(
            403,
            f"🚫 Энэ компьютер дээр «{prev_u}» хаягаар «{prev_r}» тоглолтыг дундаас нь хаяж гарсан байна! "
            f"Шинэ хаяг нээж зугтах боломжгүй. Хуучин хаягаараа буцаж орох эсвэл {mins_left} минут хүлээнэ үү.",
        )
    # 2. Max 2 new accounts per 24 hours on a single computer HWID
    new_elapsed = now - float(h_row["last_new_account_ts"] or 0.0)
    cnt_today = int(h_row["new_accounts_today"] or 0)
    if new_elapsed < 86400.0 and cnt_today >= 2:
        raise HTTPException(
            429,
            "🚫 Энэ компьютер дээр өнөөдөр шинэ хаяг нээх хязгаар тулсан байна (24 цагт дээд тал нь 2 хаяг). Хуучин хаягаараа нэвтэрнэ үү!",
        )


def _record_hwid_new_account(db, hwid: str, user_id: str, now: float):
    clean_hwid = (hwid or "").strip()[:128]
    if not clean_hwid:
        return
    h_row = db.execute("SELECT * FROM hwid_registry WHERE hwid=?", (clean_hwid,)).fetchone()
    if not h_row:
        db.execute(
            "INSERT INTO hwid_registry(hwid,last_user_id,last_new_account_ts,new_accounts_today,last_abandon_ts,last_abandon_user,last_abandon_room,total_abandons) "
            "VALUES(?,?,?,1,0,'','',0)",
            (clean_hwid, user_id, now),
        )
    else:
        new_elapsed = now - float(h_row["last_new_account_ts"] or 0.0)
        cnt = 1 if new_elapsed >= 86400.0 else (int(h_row["new_accounts_today"] or 0) + 1)
        db.execute(
            "UPDATE hwid_registry SET last_user_id=?, last_new_account_ts=?, new_accounts_today=? WHERE hwid=?",
            (user_id, now, cnt, clean_hwid),
        )


@app.post("/api/auth/register", status_code=201)
def register(data: Credentials, x_mr_hwid: str = Header(default="")):
    clean_name = data.username.strip()
    if len(clean_name) < 2 or len(clean_name) > 24:
        raise HTTPException(422, "⚠️ Тоглогчийн нэр 2–24 тэмдэгт байх ёстой.")
    if "@" in clean_name:
        raise HTTPException(422, "⚠️ Тоглогчийн нэр хэсэгт и-мэйл биш тоглолтын нэрээ бичнэ үү.")
    clean_email = (data.email or "").strip().lower()[:128]
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        raise HTTPException(422, "⚠️ И-мэйл хаягаа зөв оруулна уу (жишээ нь: name@gmail.com).")
    salt = secrets.token_hex(16)
    encoded = password_hash(data.password, salt)
    now = time.time()
    use_hwid = (data.hwid or x_mr_hwid or "").strip()[:128]
    uid = secrets.token_hex(16)
    try:
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            existing_email = db.execute("SELECT 1 FROM users WHERE lower(email)=?", (clean_email,)).fetchone()
            if existing_email:
                raise HTTPException(409, "⚠️ Энэ и-мэйл хаяг аль хэдийн бүртгэлтэй байна. И-мэйл хаягаараа шууд Нэвтрэх (Sign In) хэсгээр орно уу.")
            _check_hwid_new_account_allowed(db, use_hwid, now)
            db.execute(
                "INSERT INTO users(id,name,salt,password_hash,created,last_seen,hwid,email) VALUES(?,?,?,?,?,?,?,?)",
                (uid, clean_name, salt, encoded, now, now, use_hwid, clean_email),
            )
            _record_hwid_new_account(db, use_hwid, uid, now)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "⚠️ Энэ тоглогчийн нэр бүртгэлтэй байна. Өөр нэр сонгоно уу.")
    return {"username": clean_name, "email": clean_email}


@app.post("/api/auth/login")
def login(data: Credentials, x_mr_hwid: str = Header(default="")):
    now = time.time()
    clean_input = data.username.strip()
    clean_email = (data.email or "").strip().lower()[:128]
    use_hwid = (data.hwid or x_mr_hwid or "").strip()[:128]
    is_email_login = ("@" in clean_input and "." in clean_input.split("@")[-1])
    with database() as db:
        if is_email_login:
            row = db.execute(
                "SELECT rowid AS rowid, * FROM users WHERE lower(email)=? ORDER BY last_seen DESC LIMIT 1",
                (clean_input.lower(),),
            ).fetchone()
            if not row:
                row = db.execute("SELECT rowid AS rowid, * FROM users WHERE name=? COLLATE NOCASE", (clean_input,)).fetchone()
            if not row:
                raise HTTPException(401, "⚠️ Энэ и-мэйл хаягаар бүртгэл олдсонгүй. «Бүртгүүлэх» цэсээр бүртгүүлнэ үү.")
        else:
            row = db.execute("SELECT rowid AS rowid, * FROM users WHERE name=? COLLATE NOCASE", (clean_input,)).fetchone()
            if not row and clean_email:
                row = db.execute(
                    "SELECT rowid AS rowid, * FROM users WHERE lower(email)=? ORDER BY last_seen DESC LIMIT 1",
                    (clean_email,),
                ).fetchone()
            if not row:
                if len(clean_input) < 2 or len(clean_input) > 24:
                    raise HTTPException(422, "⚠️ Тоглогчийн нэр 2–24 тэмдэгт байх ёстой.")
                db.execute("BEGIN IMMEDIATE")
                _check_hwid_new_account_allowed(db, use_hwid, now)
                salt = secrets.token_hex(16)
                encoded = password_hash(data.password, salt)
                uid = secrets.token_hex(16)
                db.execute(
                    "INSERT INTO users(id,name,salt,password_hash,created,last_seen,hwid,email) VALUES(?,?,?,?,?,?,?,?)",
                    (uid, clean_input, salt, encoded, now, now, use_hwid, clean_email),
                )
                _record_hwid_new_account(db, use_hwid, uid, now)
                row = db.execute("SELECT rowid AS rowid, * FROM users WHERE id=?", (uid,)).fetchone()
    salt = row["salt"] if row else "00" * 16
    candidate = password_hash(data.password, salt)
    if not row or not hmac.compare_digest(candidate, row["password_hash"]):
        raise HTTPException(401, "⚠️ И-мэйл хаяг / Тоглогчийн нэр эсвэл нууц үг буруу байна.")
    token = secrets.token_urlsafe(32)
    with database() as db:
        cleanup(db)
        if clean_email and not (row["email"] or "").strip():
            db.execute("UPDATE users SET email=? WHERE id=?", (clean_email, row["id"]))
        if use_hwid:
            db.execute("UPDATE users SET last_seen=?, hwid=? WHERE id=?", (now, use_hwid, row["id"]))
            # If this computer HWID abandoned a match in the last 30 mins on another account, copy the recent abandon timestamp so room-hopping is caught!
            h_row = db.execute("SELECT * FROM hwid_registry WHERE hwid=?", (use_hwid,)).fetchone()
            if h_row and (now - float(h_row["last_abandon_ts"] or 0.0)) < 1800.0 and h_row["last_user_id"] != row["id"]:
                db.execute(
                    "UPDATE users SET last_abandon_ts=?, last_abandon_room=? WHERE id=? AND last_abandon_ts<?",
                    (h_row["last_abandon_ts"], h_row["last_abandon_room"], row["id"], h_row["last_abandon_ts"]),
                )
        else:
            db.execute("UPDATE users SET last_seen=? WHERE id=?", (now, row["id"]))
        db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash NOT IN "
                   "(SELECT token_hash FROM sessions WHERE user_id=? ORDER BY expires DESC LIMIT 4)",
                   (row["id"], row["id"]))
        db.execute("INSERT INTO sessions VALUES(?,?,?)", (digest(token), row["id"], now + SESSION_SECONDS))
        fresh_row = db.execute("SELECT rowid AS rowid, * FROM users WHERE id=?", (row["id"],)).fetchone()
    rep = _compute_user_reputation(fresh_row, now, viewer_id=fresh_row["id"])
    return {
        "token": token,
        "username": fresh_row["name"],
        "uid_num": 10000 + int(fresh_row["rowid"]),
        "expires_in": SESSION_SECONDS,
        **rep,
    }


@app.post("/api/auth/reset-password")
def reset_password(data: PasswordResetInput, x_mr_hwid: str = Header(default="")):
    clean_name = (data.username or "").strip()
    clean_email = (data.email or "").strip().lower()[:128]
    use_hwid = (data.hwid or x_mr_hwid or "").strip()[:128]
    if (not clean_email or "@" not in clean_email) and "@" in clean_name:
        clean_email = clean_name.lower()[:128]
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        raise HTTPException(422, "⚠️ И-мэйл хаягаа зөв оруулна уу (жишээ нь: name@gmail.com).")
    with database() as db:
        row = None
        if clean_name and "@" not in clean_name:
            row = db.execute("SELECT rowid AS rowid, * FROM users WHERE name=? COLLATE NOCASE", (clean_name,)).fetchone()
        if not row:
            row = db.execute(
                "SELECT rowid AS rowid, * FROM users WHERE lower(email)=? ORDER BY last_seen DESC LIMIT 1",
                (clean_email,),
            ).fetchone()
        if not row:
            raise HTTPException(404, "⚠️ Энэ и-мэйл хаяг эсвэл нэртэй тоглогч бүртгэлгүй байна.")
        stored_email = (row["email"] or "").strip().lower()
        if stored_email:
            if not hmac.compare_digest(stored_email, clean_email):
                raise HTTPException(403, "⚠️ Бүртгэлтэй и-мэйл хаяг таарахгүй байна!")
        else:
            stored_hwid = (row["hwid"] or "").strip()
            if stored_hwid and use_hwid and not hmac.compare_digest(stored_hwid, use_hwid):
                raise HTTPException(
                    403,
                    "⚠️ Энэ хаягт и-мэйл бүртгүүлээгүй байна. Анх бүртгүүлсэн компьютер дээрээсээ нууц үгээ сэргээнэ үү!",
                )
        salt = secrets.token_hex(16)
        encoded = password_hash(data.new_password, salt)
        db.execute(
            "UPDATE users SET salt=?, password_hash=?, email=? WHERE id=?",
            (salt, encoded, clean_email, row["id"]),
        )
    return {"ok": True, "username": row["name"], "detail": "✅ Нууц үг амжилттай шинэчлэгдлээ!"}


@app.post("/api/user/change-name")
def change_player_name(data: ChangeNameInput, user=Depends(current_user)):
    clean_new = (data.new_name or "").strip()
    if len(clean_new) < 2 or len(clean_new) > 24:
        raise HTTPException(422, "⚠️ Тоглогчийн нэр 2–24 тэмдэгт байх ёстой.")
    if any(ord(ch) < 32 or ch in ('"', "\\") for ch in clean_new):
        raise HTTPException(422, "⚠️ Тоглогчийн нэрэнд хориотой тэмдэгт орсон байна.")
    if "@" in clean_new:
        raise HTTPException(422, "⚠️ Тоглогчийн нэрэнд @ тэмдэгт оруулахгүй (и-мэйл биш тоглолтын нэрээ бичнэ үү).")
    old_name = user["name"]
    if clean_new == old_name:
        return {"ok": True, "username": clean_new, "detail": "✅ Тоглогчийн нэр хэвээр байна."}
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        mem = db.execute("SELECT room_id FROM members WHERE user_id=?", (user["id"],)).fetchone()
        if mem:
            wroom = w3gs_manager.get_room(mem["room_id"])
            if wroom and wroom.phase != "LOBBY":
                raise HTTPException(409, "⚠️ Тоглолт явагдаж байх үед нэр солих боломжгүй! Тоглолт дууссаны дараа солино уу.")
        conflict = db.execute(
            "SELECT id FROM users WHERE name=? COLLATE NOCASE AND id<>?",
            (clean_new, user["id"]),
        ).fetchone()
        if conflict:
            raise HTTPException(409, "⚠️ Энэ тоглогчийн нэр аль хэдийн бүртгэлтэй байна. Өөр нэр сонгоно уу.")
        db.execute("UPDATE users SET name=? WHERE id=?", (clean_new, user["id"]))
        if mem:
            wroom = w3gs_manager.get_room(mem["room_id"])
            if wroom and wroom.owner_name and wroom.owner_name.lower() == old_name.lower():
                wroom.owner_name = clean_new
    return {"ok": True, "username": clean_new, "detail": "✅ Тоглогчийн нэр амжилттай солигдлоо!"}


@app.post("/api/auth/logout")
def logout(user=Depends(current_user), authorization: str = Header()):
    with database() as db:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(authorization[7:]),))
    return {"ok": True}


@app.get("/api/rooms")
def rooms(user=Depends(current_user)):
    with database() as db:
        cleanup(db)
        rows = db.execute("SELECT r.id,r.name,r.map_name,r.capacity,r.room_code,r.no_leavers,u.name AS host,"
                          "(10000 + u.rowid) AS host_uid,"
                          "(SELECT count(*) FROM members m WHERE m.room_id=r.id) AS players "
                          "FROM rooms r JOIN users u ON u.id=r.owner ORDER BY r.rowid DESC LIMIT 200").fetchall()
    result = []
    for r in rows:
        item = dict(r)
        rc = (item.pop("room_code", "") or "").strip()
        item["is_locked"] = 1 if rc else 0
        item["no_leavers"] = int(item.get("no_leavers") or 0)
        wroom = w3gs_manager.get_room(item["id"])
        item["phase"] = wroom.phase if wroom else "LOBBY"
        if wroom and wroom.phase != "LOBBY" and wroom.peers:
            item["players"] = len(wroom.peers)
        item["w3gs_port"] = w3gs_manager.listen_port
        result.append(item)
    result.sort(key=lambda x: (0 if x.get("phase", "LOBBY") == "LOBBY" else 1, int(x.get("is_locked", 0))))
    return {"rooms": result}


@app.post("/api/rooms", status_code=201)
def create_room(data: RoomInput, user=Depends(current_user)):
    rid = secrets.token_hex(16)
    clean_code = (data.room_code or "").strip()[:32]
    no_leavers_flag = 1 if data.no_leavers else 0
    now = time.time()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        cleanup(db)
        prev_mem = db.execute("SELECT room_id FROM members WHERE user_id=?", (user["id"],)).fetchone()
        if prev_mem:
            old_rid = prev_mem["room_id"]
            _check_and_penalize_abandon_on_leave(db, old_rid, user)
            deleting_owner = db.execute("SELECT 1 FROM rooms WHERE id=? AND owner=?", (old_rid, user["id"])).fetchone()
            if deleting_owner:
                db.execute("DELETE FROM members WHERE room_id=?", (old_rid,))
                db.execute("DELETE FROM rooms WHERE id=?", (old_rid,))
                w3gs_manager.remove_room(old_rid)
            else:
                db.execute("DELETE FROM members WHERE room_id=? AND user_id=?", (old_rid, user["id"]))
        # rooms.owner is UNIQUE: remove any stale room still owned by this user (e.g. after being dropped from
        # its member list during a match) so creating a new room can never fail with a 500 IntegrityError.
        for stale in db.execute("SELECT id FROM rooms WHERE owner=?", (user["id"],)).fetchall():
            heir = db.execute(
                "SELECT u.id, u.name FROM members m JOIN users u ON u.id=m.user_id "
                "WHERE m.room_id=? AND u.id<>? AND u.id NOT IN (SELECT owner FROM rooms) LIMIT 1",
                (stale["id"], user["id"]),
            ).fetchone()
            db.execute("DELETE FROM members WHERE room_id=? AND user_id=?", (stale["id"], user["id"]))
            if heir:
                db.execute("UPDATE rooms SET owner=? WHERE id=?", (heir["id"], stale["id"]))
                w_stale = w3gs_manager.get_room(stale["id"])
                if w_stale is not None:
                    w_stale.owner_name = heir["name"]
            else:
                db.execute("DELETE FROM members WHERE room_id=?", (stale["id"],))
                db.execute("DELETE FROM rooms WHERE id=?", (stale["id"],))
                w3gs_manager.remove_room(stale["id"])
        u_fresh = db.execute("SELECT rowid AS rowid, * FROM users WHERE id=?", (user["id"],)).fetchone()
        rep = _compute_user_reputation(u_fresh, now)
        map_meta = resolve_map_meta(db, data.map_name)
        db.execute(
            "INSERT INTO rooms(id,owner,name,map_name,capacity,updated,room_code,launch_signal,no_leavers,kicked_json) VALUES(?,?,?,?,?,?,?,0,?,'[]')",
            (rid, user["id"], data.name, data.map_name, data.capacity, now, clean_code, no_leavers_flag),
        )
        db.execute("INSERT INTO members VALUES(?,?)", (user["id"], rid))
        db.execute(
            "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
            (rid, user["id"], f"👑 {user['name']} (#{user['uid_num']} • {rep['badge_short']} • {rep['elo_text']}) өрөөг үүсгэлээ.", now),
        )
    wroom = w3gs_manager.create_room(rid, data.name, user["name"], hcl=data.hcl, map_meta=map_meta)
    wroom.no_leavers = bool(no_leavers_flag)
    wroom.on_match_complete_cb = _score_w3gs_match
    wroom.on_player_dropped_cb = _on_w3gs_player_dropped
    wroom.on_chat_announce_cb = _on_w3gs_chat_announce
    wroom.on_room_remake_cb = _on_w3gs_room_remake
    return {
        "room_id": rid,
        "room_name": data.name,
        "map_name": data.map_name,
        "room_code": clean_code,
        "is_locked": 1 if clean_code else 0,
        "no_leavers": no_leavers_flag,
        "is_owner": 1,
        "launch_signal": 0,
        "w3gs_port": w3gs_manager.listen_port,
        "host_counter": wroom.host_counter,
        "entry_key": wroom.entry_key,
        "lan_ad_hex": wroom.get_lan_advertisement(6210).hex(),
        "id": map_meta.get("id", "lod_sync_25"),
        "filename": map_meta["filename"],
        "sha256": map_meta["sha256"],
        "map": {
            "id": map_meta.get("id", "lod_sync_25"),
            "filename": map_meta["filename"],
            "map_path": map_meta["map_path"],
            "file_size": map_meta["file_size"],
            "sha256": map_meta["sha256"],
            "download_url": f"/api/maps/{map_meta.get('id', map_meta['filename'])}/download",
        },
    }


@app.post("/api/rooms/{rid}/code")
def set_room_code(rid: str, data: RoomCodeInput, user=Depends(current_user)):
    clean_code = (data.room_code or "").strip()[:32]
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
        if not room:
            raise HTTPException(404, "Room not found")
        if room["owner"] != user["id"]:
            raise HTTPException(403, "Зөвхөн өрөө үүсгэсэн Host өрөөний кодыг солих эрхтэй!")
        db.execute("UPDATE rooms SET room_code=?, updated=? WHERE id=?", (clean_code, time.time(), rid))
    return {
        "ok": True,
        "room_id": rid,
        "room_code": clean_code,
        "is_locked": 1 if clean_code else 0,
    }


def _emit_join_announcements(db, rid: str, u_row, rep: dict, now: float, via_invite: bool = False):
    uid_num = 10000 + int(u_row["rowid"])
    uname = u_row["name"]
    prefix = "📨 Урилгаар" if via_invite else "➡️"
    # Use clean/neutral badge on standard join line so leaver doesn't see their own warning, while separate warning line is shown to everyone else!
    join_badge = "🌱 Шинэ тоглогч" if rep["badge_type"] == "NEWBIE" else "🛡️ Тоглогч"
    db.execute(
        "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
        (rid, u_row["id"], f"{prefix} {uname} (#{uid_num} • {join_badge} • {rep['elo_text']}) өрөөнд нэгдлээ.", now),
    )
    # PUBLIC CHAT WARNING FOR ROOM-HOPPERS / LEAVERS (hidden from the leaver's own view in room_state)!
    if rep["recent_hopper"]:
        ab_room = rep["last_abandon_room"] or "өмнөх"
        warn_msg = (
            f"🚨 [АНХААРУУЛГА] «{uname}» (#{uid_num}) саяхан «{ab_room}» тоглолтыг дуусгалгүй дундаас нь хаяж гараад "
            f"энэ өрөөнд орж ирлээ! (Нийт гарсан: {rep['leaves']} удаа • {rep['elo_text']})"
        )
        db.execute(
            "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
            (rid, u_row["id"], warn_msg, now + 0.01),
        )
    elif rep["leaves"] >= 10:
        warn_msg = (
            f"⚠️ [АНХААРУУЛГА] «{uname}» (#{uid_num}) нь {rep['leaves']} удаа тоглолтын дундаас гарсан "
            f"LEAVER тэмдэгтэй тоглогч байна! ({rep['elo_text']})"
        )
        db.execute(
            "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
            (rid, u_row["id"], warn_msg, now + 0.01),
        )


@app.post("/api/rooms/{rid}/join")
def join(rid: str, data: RoomJoinInput | None = None, user=Depends(current_user)):
    provided_code = (data.room_code if data else "").strip()
    now = time.time()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        cleanup(db)
        room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
        if not room:
            raise HTTPException(404, "Room not found")
        kicked_list = json.loads(room["kicked_json"] if "kicked_json" in room.keys() and room["kicked_json"] else "[]")
        if user["id"] in kicked_list or user["name"] in kicked_list:
            raise HTTPException(403, "👢 Та энэ өрөөнөөс Host-ийн шийдвэрээр хасагдсан (Kick) тул дахин орох боломжгүй!")
        existing = db.execute("SELECT room_id FROM members WHERE user_id=?", (user["id"],)).fetchone()
        if existing and existing[0] != rid:
            old_rid = existing[0]
            _check_and_penalize_abandon_on_leave(db, old_rid, user)
            deleting_owner = db.execute("SELECT 1 FROM rooms WHERE id=? AND owner=?", (old_rid, user["id"])).fetchone()
            if deleting_owner:
                db.execute("DELETE FROM members WHERE room_id=?", (old_rid,))
                db.execute("DELETE FROM rooms WHERE id=?", (old_rid,))
                w3gs_manager.remove_room(old_rid)
            else:
                db.execute("DELETE FROM members WHERE room_id=? AND user_id=?", (old_rid, user["id"]))
            existing = None

        u_fresh = db.execute("SELECT rowid AS rowid, * FROM users WHERE id=?", (user["id"],)).fetchone()
        rep = _compute_user_reputation(u_fresh, now)
        map_meta = resolve_map_meta(db, room["map_name"])
        wroom = ensure_w3gs_room(rid, room, db=db)
        is_viewer_only = bool(
            wroom
            and wroom.phase != "LOBBY"
            and user["name"].lower() not in {p.lower() for p in wroom.peers.keys()}
        )

        if not (existing and existing[0] == rid):
            has_invite = db.execute(
                "SELECT id FROM room_invites WHERE room_id=? AND receiver_id=?",
                (rid, user["id"]),
            ).fetchone()
            if has_invite:
                db.execute("UPDATE room_invites SET status='accepted' WHERE room_id=? AND receiver_id=?", (rid, user["id"]))
            no_leavers_on = int(room["no_leavers"] if "no_leavers" in room.keys() and room["no_leavers"] else 0) == 1
            if not is_viewer_only and no_leavers_on and room["owner"] != user["id"] and not has_invite and (rep["leaves"] >= 10 or rep["recent_hopper"] == 1):
                raise HTTPException(
                    403,
                    "🚫 Энэ өрөө «Leaver оруулахгүй» тохиргоотой тул тоглолт хаяж гарсан зөрчилтэй тоглогч орох боломжгүй!",
                )
            required_code = (room["room_code"] if "room_code" in room.keys() else "").strip()
            if required_code and room["owner"] != user["id"] and not has_invite:
                if not hmac.compare_digest(required_code, provided_code):
                    raise HTTPException(403, "Өрөөний нууц код буруу байна!")
            count = db.execute("SELECT count(*) FROM members WHERE room_id=?", (rid,)).fetchone()[0]
            if not is_viewer_only and count >= room["capacity"]:
                raise HTTPException(409, "Room is full")
            db.execute("INSERT INTO members VALUES(?,?)", (user["id"], rid))
            if not is_viewer_only:
                _emit_join_announcements(db, rid, u_fresh, rep, now, via_invite=bool(has_invite))
        launch_sig = int(room["launch_signal"] if "launch_signal" in room.keys() else 0)
        is_owner = 1 if room["owner"] == user["id"] else 0
    return {
        "ok": True,
        "room_id": rid,
        "room_name": room["name"],
        "map_name": room["map_name"],
        "is_owner": is_owner,
        "launch_signal": launch_sig,
        "w3gs_port": w3gs_manager.listen_port,
        "phase": wroom.phase,
        "host_counter": wroom.rejoin_counter if wroom.phase in ("WAITING", "LOADING") else wroom.host_counter,
        "entry_key": wroom.entry_key,
        "lan_ad_hex": wroom.get_lan_advertisement(6210).hex(),
        "id": map_meta.get("id", "lod_sync_25"),
        "filename": map_meta["filename"],
        "sha256": map_meta["sha256"],
        "map": {
            "id": map_meta.get("id", "lod_sync_25"),
            "filename": map_meta["filename"],
            "map_path": map_meta["map_path"],
            "file_size": map_meta["file_size"],
            "sha256": map_meta["sha256"],
            "download_url": f"/api/maps/{map_meta.get('id', map_meta['filename'])}/download",
        },
    }


@app.post("/api/rooms/{rid}/kick")
async def kick_room_member(rid: str, data: TargetUserInput, user=Depends(current_user)):
    def _db_kick():
        now = time.time()
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
            if not room:
                raise HTTPException(404, "Өрөө олдсонгүй")
            if room["owner"] != user["id"]:
                raise HTTPException(403, "Зөвхөн өрөөний Host тоглогч гаргах (Kick) эрхтэй!")
            t_row = _resolve_target_user(db, data.target)
            if not t_row:
                raise HTTPException(404, "Тоглогч олдсонгүй")
            if t_row["id"] == user["id"]:
                raise HTTPException(400, "Өөрийгөө өрөөнөөс Kick хийх боломжгүй!")
            db.execute("DELETE FROM members WHERE room_id=? AND user_id=?", (rid, t_row["id"]))
            kicked_list = json.loads(room["kicked_json"] if "kicked_json" in room.keys() and room["kicked_json"] else "[]")
            if t_row["id"] not in kicked_list:
                kicked_list.append(t_row["id"])
            if t_row["name"] not in kicked_list:
                kicked_list.append(t_row["name"])
            db.execute("UPDATE rooms SET kicked_json=?, updated=? WHERE id=?", (json.dumps(kicked_list), now, rid))
            db.execute(
                "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
                (rid, user["id"], f"👢 Host «{t_row['name']}» (#{10000 + int(t_row['rowid'])})-ийг өрөөнөөс гаргалаа (Kick).", now),
            )
            return t_row["name"], w3gs_manager.get_room(rid)

    target_name, wroom = await asyncio.to_thread(_db_kick)
    if wroom:
        await wroom.kick_player(target_name, "Host өрөөнөөс гаргалаа")
    return {"ok": True, "kicked": target_name}


@app.get("/api/rooms/{rid}/state")
def room_state(rid: str, local_port: int = 6210, ping_ms: int = 0, ui: int = 0, user=Depends(current_user)):
    now = time.time()
    with database() as db:
        room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
        if not room:
            raise HTTPException(404, "Room not found")
        if not db.execute("SELECT 1 FROM members WHERE room_id=? AND user_id=?", (rid, user["id"])).fetchone():
            raise HTTPException(403, "Та энэ өрөөнөөс гарсан эсвэл Host таныг өрөөнөөс гаргасан (Kick) байна.")
        if 0 < ping_ms < 9999 and abs(int(ping_ms) - int(user.get("ping_ms") or 0)) >= 3:
            db.execute("UPDATE users SET ping_ms=? WHERE id=?", (int(ping_ms), user["id"]))
        if (now - float(room["updated"] or 0)) >= 5.0:
            db.execute("UPDATE rooms SET updated=? WHERE id=?", (now, rid))
        host_row = db.execute("SELECT name FROM users WHERE id=?", (room["owner"],)).fetchone()
        host_name = host_row["name"] if host_row else "Host"
        wroom = ensure_w3gs_room(rid, room, host_name=host_name, db=db)
        wroom.updated_at = now
        mem_rows = db.execute(
            "SELECT u.rowid AS rowid, u.* "
            "FROM members m JOIN users u ON u.id=m.user_id WHERE m.room_id=? "
            "ORDER BY (u.id = ?) DESC, u.name ASC",
            (rid, room["owner"]),
        ).fetchall()
        blocked_ids = {
            r[0] for r in db.execute("SELECT blocked_id FROM blocks WHERE user_id=?", (user["id"],)).fetchall()
        }
        msg_rows = db.execute(
            "SELECT m.id, m.user_id, u.rowid AS rowid, u.name AS username, m.text, m.created "
            "FROM messages m JOIN users u ON u.id=m.user_id WHERE m.room_id=? ORDER BY m.id DESC LIMIT 60",
            (rid,),
        ).fetchall()
    rc = (room["room_code"] if "room_code" in room.keys() else "").strip()
    launch_sig = int(room["launch_signal"] if "launch_signal" in room.keys() else 0)
    no_leavers_flag = int(room["no_leavers"] if "no_leavers" in room.keys() and room["no_leavers"] else 0)
    is_owner = (room["owner"] == user["id"])
    w3gs_conn_cnt = sum(1 for p in wroom.peers.values() if p.writer is not None)
    members_out = []
    for m in mem_rows:
        m_rep = _compute_user_reputation(m, now, viewer_id=user["id"])
        w3gs_conn = 1 if (m["name"] in wroom.peers and wroom.peers[m["name"]].writer is not None) else 0
        live_st = wroom.player_stats.get(m["name"], {})
        m_ping = int(m["ping_ms"] if "ping_ms" in m.keys() and m["ping_ms"] else 12)
        if m_ping <= 0 or m_ping >= 9999:
            m_ping = 12
        members_out.append({
            "uid_num": 10000 + int(m["rowid"]),
            "name": m["name"],
            "is_host": 1 if m["id"] == room["owner"] else 0,
            "w3gs_connected": w3gs_conn,
            "ping_ms": m_ping,
            "live_kills": int(live_st.get("kills", 0)),
            "live_deaths": int(live_st.get("deaths", 0)),
            **m_rep,
        })
    messages_out = [
        {
            "id": m["id"],
            "uid_num": 10000 + int(m["rowid"]),
            "username": m["username"],
            "sender": m["username"],
            "text": m["text"],
            "message": m["text"],
            "created_at": int(m["created"]),
            "time_str": time.strftime("%H:%M", time.localtime(m["created"])),
        }
        for m in reversed(msg_rows)
        if m["user_id"] not in blocked_ids
        and not m["text"].startswith("⏱️ [КОМАНДЫН ЗААВАР]")
        and not (
            m["user_id"] == user["id"]
            and (m["text"].startswith("🚨 [АНХААРУУЛГА]") or m["text"].startswith("⚠️ [АНХААРУУЛГА]"))
        )
    ]
    wait_rem = wroom.get_wait_remaining_sec()
    my_w3gs_conn = 1 if (user["name"] in wroom.peers and wroom.peers[user["name"]].writer is not None) else 0
    my_disc = 1 if (wroom.phase != "LOBBY" and (wroom.absent == user["name"] or user["name"] in wroom.disconnected_players)) else 0
    can_drop = 1 if (is_owner and wroom.absent and wroom.absent != user["name"] and wroom.phase in ("FROZEN", "WAITING", "LOADING") and (wait_rem <= 0 or w3gs_conn_cnt == 0)) else 0
    return {
        "room_id": rid,
        "name": wroom.name,
        "host": host_name,
        "map_name": room["map_name"],
        "capacity": room["capacity"],
        "phase": wroom.phase,
        "is_locked": 1 if rc else 0,
        "no_leavers": no_leavers_flag,
        "room_code": rc if is_owner else "",
        "is_owner": 1 if is_owner else 0,
        "launch_signal": launch_sig,
        "w3gs_connected_count": w3gs_conn_cnt,
        "my_w3gs_connected": my_w3gs_conn,
        "my_disconnected": my_disc,
        "wait_remaining_sec": wait_rem,
        "wait_total_sec": int(wroom.wait_duration_sec),
        "addtime_used": int(wroom.addtime_count),
        "addtime_max": int(wroom.addtime_max),
        "can_host_drop": can_drop,
        "rejoin_ready": 1 if (my_disc and wroom.phase in ("WAITING", "LOADING") and wroom.checkpoint_info) else 0,
        "match_active": 1 if (wroom.phase != "LOBBY" and wroom.match_started_at > 0) else 0,
        "w3gs_port": w3gs_manager.listen_port,
        "host_counter": wroom.host_counter,
        "rejoin_counter": wroom.rejoin_counter,
        "entry_key": wroom.entry_key,
        "absent": wroom.absent or "",
        "absent_player": wroom.absent or "",
        "save_name": wroom.save_name,
        "checkpoint": (
            {
                "filename": wroom.checkpoint_info["filename"],
                "sha256": wroom.checkpoint_info["sha256"],
                "bytes": wroom.checkpoint_info["bytes"],
                "random_seed": wroom.checkpoint_info["random_seed"],
                "magic": wroom.checkpoint_info["magic"],
            }
            if wroom.checkpoint_info
            else None
        ),
        "lan_ad_hex": wroom.get_lan_advertisement(local_port).hex(),
        "slots": [dict(s) for s in wroom.slots[:10]],
        "members": members_out,
        "messages": messages_out,
        "players": [
            {
                "name": p.name,
                "pid": p.pid,
                "sid": p.sid,
                "loaded": p.loaded,
                "map_ready": p.map_ready,
                "connected": p.writer is not None,
            }
            for p in wroom.peers.values()
        ],
        "events": list(wroom.events)[-25:],
    }


@app.post("/api/rooms/{rid}/launch")
async def launch_room_game(rid: str, user=Depends(current_user)):
    def _db_launch():
        now = time.time()
        sig = int(now)
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            require_member(db, rid, user)
            room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
            if not room:
                raise HTTPException(404, "Room not found")
            if room["owner"] != user["id"]:
                raise HTTPException(403, "Зөвхөн өрөө үүсгэсэн Host тоглоомыг эхлүүлэх эрхтэй!")
            mem_names = [
                r[0]
                for r in db.execute(
                    "SELECT u.name FROM members m JOIN users u ON u.id=m.user_id WHERE m.room_id=?",
                    (rid,),
                ).fetchall()
            ]
            db.execute("UPDATE rooms SET launch_signal=?, updated=? WHERE id=?", (sig, now, rid))
            db.execute(
                "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
                (rid, user["id"], "🚀 Host тоглоомыг эхлүүллээ! Бүх тоглогчдын Warcraft III автоматаар асч байна...", now),
            )
            return sig, mem_names, ensure_w3gs_room(rid, room, host_name=user["name"], db=db)

    sig, mem_names, wroom = await asyncio.to_thread(_db_launch)
    if wroom.phase == "STARTING" and wroom.match_started_at <= 0.0:
        wroom.phase = "LOBBY"
    started = False
    host_peer = wroom.peers.get(user["name"])
    all_members_in_w3gs = bool(mem_names) and all(
        (m in wroom.peers and wroom.peers[m].writer is not None and wroom.peers[m].map_ready)
        for m in mem_names
    )
    if wroom.phase == "LOBBY" and host_peer is not None and host_peer.writer is not None and host_peer.map_ready and all_members_in_w3gs:
        started = await wroom.start_game(force=True)
    return {"ok": True, "launch_signal": sig, "w3gs_started": started, "phase": wroom.phase}


@app.post("/api/rooms/{rid}/start")
async def start_room_game(rid: str, user=Depends(current_user)):
    def _db_start():
        with database() as db:
            require_member(db, rid, user)
            room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
            if not room:
                raise HTTPException(404, "Room not found")
            if room["owner"] != user["id"]:
                raise HTTPException(403, "Зөвхөн өрөө үүсгэсэн Host тоглоомыг эхлүүлэх эрхтэй!")
            return ensure_w3gs_room(rid, room, host_name=user["name"], db=db)

    wroom = await asyncio.to_thread(_db_start)
    started = await wroom.start_game(force=True)
    return {"ok": started, "phase": wroom.phase}


@app.post("/api/rooms/{rid}/addtime")
async def extend_room_wait_time(rid: str, user=Depends(current_user)):
    def _db_get_wroom():
        with database() as db:
            require_member(db, rid, user)
            room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
            if not room:
                raise HTTPException(404, "Room not found")
            host_row = db.execute("SELECT name FROM users WHERE id=?", (room["owner"],)).fetchone()
            host_name = host_row["name"] if host_row else "Host"
            return ensure_w3gs_room(rid, room, host_name=host_name, db=db)

    wroom = await asyncio.to_thread(_db_get_wroom)
    ok, reply_msg, rem = await wroom.add_wait_time(user["name"])
    if not ok:
        raise HTTPException(400, reply_msg)

    def _db_post_msg():
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
                (rid, user["id"], reply_msg, time.time()),
            )

    await asyncio.to_thread(_db_post_msg)
    return {
        "ok": True,
        "message": reply_msg,
        "wait_remaining_sec": rem,
        "addtime_used": wroom.addtime_count,
        "addtime_max": wroom.addtime_max,
    }


@app.post("/api/rooms/{rid}/drop")
async def drop_absent_room_member(rid: str, user=Depends(current_user)):
    def _db_drop():
        with database() as db:
            require_member(db, rid, user)
            room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
            if not room:
                raise HTTPException(404, "Room not found")
            if room["owner"] != user["id"]:
                raise HTTPException(403, "Зөвхөн өрөөний Host хүлээх хугацаа дууссаны дараа тоглогчийг Drop хийх эрхтэй!")
            return ensure_w3gs_room(rid, room, host_name=user["name"], db=db)

    wroom = await asyncio.to_thread(_db_drop)
    ok, reply_msg = await wroom.drop_absent_player_by_host(user["name"])
    if not ok:
        raise HTTPException(400, reply_msg)
    return {"ok": True, "message": reply_msg, "phase": wroom.phase}


@app.put("/api/rooms/{rid}/checkpoint")
@app.post("/api/rooms/{rid}/checkpoint")
async def upload_checkpoint(rid: str, request: Request, user=Depends(current_user)):
    body = await request.body()

    def _db_upload():
        with database() as db:
            require_member(db, rid, user)
            room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
            if not room:
                raise HTTPException(404, "Room not found")
            wroom = ensure_w3gs_room(rid, room, db=db)
            db.execute("UPDATE rooms SET updated=? WHERE id=?", (time.time(), rid))
            return wroom

    wroom = await asyncio.to_thread(_db_upload)
    try:
        info = wroom.receive_checkpoint_bytes(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {
        "ok": True,
        "filename": info["filename"],
        "sha256": info["sha256"],
        "bytes": info["bytes"],
        "random_seed": info["random_seed"],
    }


@app.get("/api/rooms/{rid}/checkpoint")
def download_checkpoint(rid: str, user=Depends(current_user)):
    with database() as db:
        require_member(db, rid, user)
        wroom = w3gs_manager.get_room(rid)
    if not wroom or not wroom.checkpoint_bytes or not wroom.checkpoint_info:
        raise HTTPException(404, "No checkpoint staged for this room")
    fname = wroom.checkpoint_info["filename"]
    return Response(
        content=wroom.checkpoint_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/rooms/{rid}/heartbeat")
async def heartbeat(rid: str, data: HeartbeatInput | None = None, user=Depends(current_user)):
    violation = (data.violation if data else "").strip()
    if violation:
        wroom = w3gs_manager.get_room(rid)
        if wroom:
            await wroom.report_and_kick_cheater(user["name"], violation)

        def _db_del_violator():
            with database() as db:
                db.execute("DELETE FROM members WHERE room_id=? AND user_id=?", (rid, user["id"]))

        await asyncio.to_thread(_db_del_violator)
        raise HTTPException(403, f"Anti-MapHack Violation: {violation}")

    def _db_hb():
        now = time.time()
        with database() as db:
            cleanup(db)
            if data and 0 < data.ping_ms < 9999 and abs(int(data.ping_ms) - int(user.get("ping_ms") or 0)) >= 3:
                db.execute("UPDATE users SET ping_ms=? WHERE id=?", (int(data.ping_ms), user["id"]))
            wroom = w3gs_manager.get_room(rid)
            if wroom and wroom.phase != "LOBBY":
                require_member(db, rid, user)
                db.execute("UPDATE rooms SET updated=? WHERE id=? AND updated<?", (now, rid, now - 5.0))
                wroom.updated_at = now
                return {"ok": True}
            if data is None:
                if not db.execute("UPDATE rooms SET updated=? WHERE id=? AND owner=?", (now, rid, user["id"])).rowcount:
                    raise HTTPException(403, "Only the room host can send heartbeats")
            else:
                db.execute("UPDATE rooms SET updated=? WHERE id=? AND updated<?", (now, rid, now - 5.0))
        return {"ok": True}

    return await asyncio.to_thread(_db_hb)


@app.post("/api/rooms/{rid}/leave")
async def leave(rid: str, force: int = 0, user=Depends(current_user)):
    wroom = w3gs_manager.get_room(rid)
    if wroom and wroom.absent == user["name"] and wroom.phase in ("FROZEN", "WAITING", "LOADING"):
        if not force and wroom.get_wait_remaining_sec() > 0:
            raise HTTPException(
                403,
                f"Тоглолт түр зогссон (Rejoin хүлээх хугацаа: {wroom.get_wait_remaining_sec()} сек үлдсэн) тул өрөөнөөс гарах боломжгүй!",
            )
        try:
            await wroom.drop_absent_player_by_host(user["name"], allow_self=True)
        except Exception:
            pass

    def _db_leave():
        now = time.time()
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
            if not room:
                db.execute("DELETE FROM members WHERE room_id=? AND user_id=?", (rid, user["id"]))
                w3gs_manager.remove_room(rid)
                return {"ok": True, "room_closed": True}
            is_active_peer = bool(
                wroom
                and user["name"].lower() in {p.lower() for p in wroom.peers.keys()}
            )
            if not force and is_active_peer and wroom and wroom.absent and wroom.phase in ("FROZEN", "WAITING", "LOADING") and wroom.get_wait_remaining_sec() > 0:
                raise HTTPException(
                    403,
                    f"Тоглолт түр зогссон (Rejoin хүлээх хугацаа: {wroom.get_wait_remaining_sec()} сек үлдсэн) тул өрөөнөөс гарах боломжгүй!",
                )
            _check_and_penalize_abandon_on_leave(db, rid, user)
            deleting_owner = (room["owner"] == user["id"])
            active_peers = sum(1 for p in wroom.peers.values() if p.writer is not None and p.name != user["name"]) if wroom else 0
            if deleting_owner and wroom and wroom.phase != "LOBBY" and active_peers > 0:
                db.execute("DELETE FROM members WHERE room_id=? AND user_id=?", (rid, user["id"]))
                heir = db.execute(
                    "SELECT u.id, u.name FROM members m JOIN users u ON u.id=m.user_id "
                    "WHERE m.room_id=? AND u.id NOT IN (SELECT owner FROM rooms) LIMIT 1",
                    (rid,),
                ).fetchone()
                if heir:
                    db.execute("UPDATE rooms SET owner=?, updated=? WHERE id=?", (heir["id"], now, rid))
                    wroom.owner_name = heir["name"]
                    db.execute(
                        "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
                        (rid, heir["id"], f"⬅️ Host {user['name']} өрөөнөөс гарсан тул «{heir['name']}» шинэ Host боллоо.", now),
                    )
                    return {"ok": True, "room_closed": False}
            if deleting_owner:
                db.execute("DELETE FROM members WHERE room_id=?", (rid,))
                db.execute("DELETE FROM rooms WHERE id=?", (rid,))
                if wroom and not wroom.match_scored and wroom.match_started_at > 0 and (now - wroom.match_started_at) >= 180:
                    try:
                        _score_w3gs_match(wroom)
                    except Exception:
                        pass
                w3gs_manager.remove_room(rid)
                return {"ok": True, "room_closed": True}
            else:
                db.execute("DELETE FROM members WHERE room_id=? AND user_id=?", (rid, user["id"]))
                if not wroom or wroom.phase == "LOBBY" or is_active_peer:
                    db.execute(
                        "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
                        (rid, user["id"], f"⬅️ {user['name']} өрөөнөөс гарлаа.", now),
                    )
                return {"ok": True, "room_closed": False}

    return await asyncio.to_thread(_db_leave)


@app.get("/api/rooms/{rid}/messages")
def messages(rid: str, after: int = 0, user=Depends(current_user)):
    with database() as db:
        require_member(db, rid, user)
        rows = db.execute("SELECT m.id,u.name AS username,m.text,m.created FROM messages m "
                          "JOIN users u ON u.id=m.user_id WHERE room_id=? AND m.id>? ORDER BY m.id LIMIT 100",
                          (rid, after)).fetchall()
    return {"messages": [dict(r) for r in rows]}


@app.post("/api/rooms/{rid}/messages", status_code=201)
@app.post("/api/rooms/{rid}/chat", status_code=201)
async def message(rid: str, data: ChatInput, user=Depends(current_user)):
    msg_text = (data.text or data.message or "").strip()
    if not msg_text:
        raise HTTPException(400, "Empty message")
    low_cmd = msg_text.lower()
    wroom = w3gs_manager.get_room(rid)

    def _db_insert_msg(text_val: str, prune: bool = False) -> int:
        now_t = time.time()
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            require_member(db, rid, user)
            if not prune:
                recent = db.execute(
                    "SELECT id, text FROM messages WHERE room_id=? AND created>? ORDER BY id DESC LIMIT 1",
                    (rid, now_t - 2.0),
                ).fetchone()
                if recent and (
                    recent["text"] == text_val
                    or (len(recent["text"]) >= 25 and text_val.startswith(recent["text"][:25]))
                    or (len(text_val) >= 25 and recent["text"].startswith(text_val[:25]))
                ):
                    return recent["id"]
            cursor = db.execute(
                "INSERT INTO messages(room_id,user_id,text,created) VALUES(?,?,?,?)",
                (rid, user["id"], text_val, now_t),
            )
            mid_val = cursor.lastrowid
            if prune:
                db.execute(
                    "DELETE FROM messages WHERE room_id=? AND id NOT IN "
                    "(SELECT id FROM messages WHERE room_id=? ORDER BY id DESC LIMIT 100)",
                    (rid, rid),
                )
            return mid_val

    if low_cmd.startswith(("-", "!", "/")) and wroom:
        cmd_parts = msg_text[1:].split()
        cmd_head = cmd_parts[0].lower() if cmd_parts else ""
        is_room_host = wroom._is_effective_host(user["name"])
        if cmd_head == "swap":
            if not is_room_host:
                return {"id": 0, "ok": False, "message": ""}
            if wroom.phase != "LOBBY":
                return {"id": 0, "ok": False, "message": ""}
            if len(cmd_parts) >= 3:
                try:
                    s1, s2 = int(cmd_parts[1]) - 1, int(cmd_parts[2]) - 1
                    await wroom.swap_slots(s1, s2)
                    rep_txt = f"🔄 {cmd_parts[1]}-р болон {cmd_parts[2]}-р суудлыг солилоо (-swap {cmd_parts[1]} {cmd_parts[2]})."
                    await wroom.send_all_chat(f"|cFF00FF88[Host]|r {rep_txt}")
                    mid = await asyncio.to_thread(_db_insert_msg, rep_txt)
                    return {"id": mid, "ok": True, "message": rep_txt}
                except ValueError:
                    pass
            return {"id": 0, "ok": False, "message": ""}
    mid = await asyncio.to_thread(_db_insert_msg, msg_text, True)
    return {"id": mid, "ok": True}


@app.post("/api/rooms/{rid}/slot")
async def room_slot_action(rid: str, data: SlotActionInput, user=Depends(current_user)):
    wroom = w3gs_manager.get_room(rid)
    if not wroom:
        raise HTTPException(404, "Room not found")
    act = (data.action or "").strip().lower()
    if act == "map":
        def _db_update_map():
            with database() as db:
                db.execute("BEGIN IMMEDIATE")
                require_member(db, rid, user)
                room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
                if not room:
                    raise HTTPException(404, "Room not found")
                if room["owner"] != user["id"] and not wroom._is_effective_host(user["name"]):
                    raise HTTPException(403, "Only host can change map")
                raw_map = (data.map_name or "").strip()
                if not raw_map:
                    return None
                meta = resolve_map_meta(db, raw_map)
                db.execute("UPDATE rooms SET map_name=?, updated=? WHERE id=?", (meta["filename"], time.time(), rid))
                return meta
        meta = await asyncio.to_thread(_db_update_map)
        if meta:
            await wroom.update_map_meta(meta)
        return {
            "ok": True,
            "map_name": meta["filename"] if meta else wroom.map_name,
            "lan_ad_hex": wroom.get_lan_advertisement(6210).hex(),
            "slots": [dict(s) for s in wroom.slots[:10]],
        }
    ok, msg = await wroom.host_set_slot(user["name"], act, int(data.slot or 0), int(data.target_slot or 0))
    return {
        "ok": ok,
        "message": msg,
        "phase": wroom.phase,
        "slots": [dict(s) for s in wroom.slots[:10]],
    }


# ---------------------------------------------------------------------------
# SOCIAL, FRIENDS, DIRECT CHAT, USER PROFILE, BLOCK, INVITES & LEADERBOARD API
# ---------------------------------------------------------------------------

@app.get("/api/leaderboard")
def get_leaderboard(user=Depends(current_user)):
    now = time.time()
    with database() as db:
        rows = db.execute(
            "SELECT rowid AS rowid, * FROM users "
            "WHERE name NOT LIKE 'Host\\_%' ESCAPE '\\' "
            "AND name NOT LIKE 'Peer\\_%' ESCAPE '\\' "
            "AND name NOT LIKE 'test\\_%' ESCAPE '\\' "
            "AND name NOT LIKE 'Smoke%' "
            "AND name NOT LIKE 'bot\\_%' ESCAPE '\\' "
            "ORDER BY (games_played >= 10) DESC, elo DESC, kills DESC, games_played DESC LIMIT 100"
        ).fetchall()
    leaders = []
    for idx, r in enumerate(rows, start=1):
        rep = _compute_user_reputation(r, now, viewer_id=user["id"])
        u_ping = int(r["ping_ms"] if "ping_ms" in r.keys() and r["ping_ms"] else 12)
        if u_ping <= 0 or u_ping >= 9999:
            u_ping = 12
        leaders.append({
            "rank": idx,
            "uid_num": 10000 + int(r["rowid"]),
            "name": r["name"],
            "username": r["name"],
            "online": 1 if (now - float(r["last_seen"] or 0)) < 35.0 else 0,
            "ping_ms": u_ping,
            **rep,
        })
    return {"ok": True, "leaders": leaders, "leaderboard": leaders}


@app.post("/api/debug/dump")
async def upload_debug_dump(request: Request, name: str = "", user=Depends(current_user)):
    """Stores a Warcraft III MRDump state file (rejoin desync diagnostics) uploaded by the client."""
    clean = re.sub(r"[^A-Za-z0-9_.-]", "_", (name or "dump.txt"))[:64]
    body = await request.body()
    d = Path(os.environ.get("MONGOLRANGER_DEBUG_DIR", str(DB_PATH.resolve().parent / "debug")))
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"dump_{int(time.time())}_{re.sub(r'[^A-Za-z0-9_]', '_', user['name'])}_{clean}"
    out.write_bytes(body)
    return {"ok": True, "bytes": len(body)}


@app.get("/api/users/search")
def search_users(q: str = "", user=Depends(current_user)):
    """Autocomplete for the Friends tab: returns matching players to pick from (never sends a request itself)."""
    now = time.time()
    clean = (q or "").strip().lstrip("#")[:24]
    if not clean:
        return {"ok": True, "users": []}
    with database() as db:
        params: list = [user["id"]]
        where = (
            "u.id<>? "
            "AND u.name NOT LIKE 'Host\\_%' ESCAPE '\\' "
            "AND u.name NOT LIKE 'Peer\\_%' ESCAPE '\\' "
            "AND u.name NOT LIKE 'test\\_%' ESCAPE '\\' "
            "AND u.name NOT LIKE 'Smoke%' "
            "AND u.name NOT LIKE 'bot\\_%' ESCAPE '\\' "
            "AND (u.name LIKE ? ESCAPE '\\'"
        )
        like = clean.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        params.append(like)
        if clean.isdigit():
            num = int(clean)
            where += " OR u.rowid=?"
            params.append(num - 10000 if num > 10000 else num)
        where += ")"
        rows = db.execute(
            f"SELECT u.rowid AS rowid, u.* FROM users u WHERE {where} ORDER BY length(u.name), u.name LIMIT 15",
            params,
        ).fetchall()
        result = []
        for r in rows:
            fr = db.execute(
                "SELECT user_id, status FROM friendships WHERE (user_id=? AND friend_id=?) OR (user_id=? AND friend_id=?)",
                (user["id"], r["id"], r["id"], user["id"]),
            ).fetchall()
            status = "none"
            for f in fr:
                if f["status"] == "accepted":
                    status = "accepted"
                    break
                if f["status"] == "pending":
                    status = "pending_out" if f["user_id"] == user["id"] else "pending_in"
            rep = _compute_user_reputation(r, now, viewer_id=user["id"])
            result.append({
                "name": r["name"],
                "uid_num": 10000 + int(r["rowid"]),
                "online": 1 if (now - float(r["last_seen"] or 0)) < 35.0 else 0,
                "friendship_status": status,
                "badge_label": rep["badge_label"],
                "badge_color": rep["badge_color"],
                "elo_display": rep["elo_display"],
                "elo_color": rep["elo_color"],
            })
    return {"ok": True, "users": result}


@app.get("/api/users/matches")
def user_match_history(q: str = "", user=Depends(current_user)):
    """Last 10 matches of a player (self by default) for the profile history cards."""
    now = time.time()
    with database() as db:
        t_row = _resolve_target_user(db, q) if (q or "").strip() else db.execute(
            "SELECT rowid AS rowid, * FROM users WHERE id=?", (user["id"],)
        ).fetchone()
        if not t_row:
            raise HTTPException(404, "Хэрэглэгч олдсонгүй")
        rows = db.execute(
            "SELECT * FROM match_history WHERE user_id=? ORDER BY id DESC LIMIT 10", (t_row["id"],)
        ).fetchall()
        rep = _compute_user_reputation(t_row, now, viewer_id=user["id"])
    matches = []
    for r in rows:
        try:
            mates = json.loads(r["teammates_json"] or "[]")
        except ValueError:
            mates = []
        try:
            opps = json.loads(r["opponents_json"] or "[]")
        except ValueError:
            opps = []
        matches.append({
            "id": r["id"],
            "result": r["result"],
            "room_name": r["room_name"],
            "map_name": r["map_name"],
            "kills": r["kills"],
            "deaths": r["deaths"],
            "assists": r["assists"],
            "team": r["team"],
            "team_name": "Sentinel" if int(r["team"]) == 0 else "Scourge",
            "teammates": mates,
            "opponents": opps,
            "teammates_text": ", ".join(m.get("name", "") for m in mates) or "-",
            "opponents_text": ", ".join(m.get("name", "") for m in opps) or "-",
            "elo_delta": r["elo_delta"],
            "elo_after": r["elo_after"],
            "duration_sec": r["duration_sec"],
            "created_at": int(r["created"]),
            "date_str": time.strftime("%Y-%m-%d %H:%M", time.localtime(r["created"])),
        })
    return {"ok": True, "username": t_row["name"], "uid_num": 10000 + int(t_row["rowid"]), **rep, "matches": matches}


@app.get("/api/users/info")
def get_user_info(target: str = "", q: str = "", user=Depends(current_user)):
    now = time.time()
    query_val = (q or target or "").strip()
    with database() as db:
        cleanup(db)
        t_row = _resolve_target_user(db, query_val)
        if not t_row:
            raise HTTPException(404, "Хэрэглэгч олдсонгүй")
        tid = t_row["id"]
        uid_num = 10000 + int(t_row["rowid"])
        online_bool = (now - float(t_row["last_seen"] or 0)) < 35.0
        created_ts = int(float(t_row["created"] or now))
        created_date = time.strftime("%Y-%m-%d", time.localtime(created_ts))
        rm = db.execute(
            "SELECT r.id, r.name, r.map_name FROM members m JOIN rooms r ON r.id=m.room_id WHERE m.user_id=?",
            (tid,),
        ).fetchone()
        fr_out = db.execute(
            "SELECT status FROM friendships WHERE user_id=? AND friend_id=?",
            (user["id"], tid),
        ).fetchone()
        fr_in = db.execute(
            "SELECT status FROM friendships WHERE user_id=? AND friend_id=?",
            (tid, user["id"]),
        ).fetchone()
        blk = db.execute(
            "SELECT 1 FROM blocks WHERE user_id=? AND blocked_id=?",
            (user["id"], tid),
        ).fetchone()
        rep = _compute_user_reputation(t_row, now, viewer_id=user["id"])
    friend_state = 0
    f_status_str = "none"
    if tid == user["id"]:
        f_status_str = "self"
    elif (fr_out and fr_out["status"] == "accepted") or (fr_in and fr_in["status"] == "accepted"):
        friend_state = 1
        f_status_str = "accepted"
    elif fr_out and fr_out["status"] == "pending":
        friend_state = 2
        f_status_str = "pending_out"
    elif fr_in and fr_in["status"] == "pending":
        friend_state = 3
        f_status_str = "pending_in"
    t_ping = int(t_row["ping_ms"] if "ping_ms" in t_row.keys() and t_row["ping_ms"] else 12)
    if t_ping <= 0 or t_ping >= 9999:
        t_ping = 12
    return {
        "ok": True,
        "uid_num": uid_num,
        "name": t_row["name"],
        "username": t_row["name"],
        "online": online_bool,
        "ping_ms": t_ping,
        "created_at": created_ts,
        "created_date": created_date,
        "room_id": rm["id"] if rm else "",
        "room_name": rm["name"] if rm else "",
        "current_room_name": rm["name"] if rm else "",
        "map_name": rm["map_name"] if rm else "",
        "is_friend": friend_state,
        "friendship_status": f_status_str,
        "is_blocked": bool(blk),
        **rep,
    }


@app.post("/api/friends/request")
def send_friend_request(data: TargetUserInput, user=Depends(current_user)):
    now = time.time()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        t_row = _resolve_target_user(db, data.target)
        if not t_row:
            raise HTTPException(404, "Хэрэглэгч олдсонгүй! Нэр эсвэл #ID дугаарыг шалгана уу.")
        tid = t_row["id"]
        if tid == user["id"]:
            raise HTTPException(400, "Өөр рүүгээ найзын хүсэлт илгээх боломжгүй!")
        blocked = db.execute(
            "SELECT 1 FROM blocks WHERE (user_id=? AND blocked_id=?) OR (user_id=? AND blocked_id=?)",
            (user["id"], tid, tid, user["id"]),
        ).fetchone()
        if blocked:
            raise HTTPException(403, "Блок хийгдсэн хэрэглэгч байна.")
        rev = db.execute(
            "SELECT status FROM friendships WHERE user_id=? AND friend_id=?",
            (tid, user["id"]),
        ).fetchone()
        if rev:
            db.execute(
                "UPDATE friendships SET status='accepted' WHERE user_id=? AND friend_id=?",
                (tid, user["id"]),
            )
            db.execute(
                "INSERT OR REPLACE INTO friendships(user_id,friend_id,status,created) VALUES(?,?,?,?)",
                (user["id"], tid, "accepted", now),
            )
            return {"ok": True, "status": "accepted", "name": t_row["name"], "target": t_row["name"], "uid_num": 10000 + int(t_row["rowid"])}
        existing = db.execute(
            "SELECT status FROM friendships WHERE user_id=? AND friend_id=?",
            (user["id"], tid),
        ).fetchone()
        if existing and existing["status"] == "accepted":
            return {"ok": True, "status": "accepted", "name": t_row["name"], "target": t_row["name"], "uid_num": 10000 + int(t_row["rowid"])}
        db.execute(
            "INSERT OR REPLACE INTO friendships(user_id,friend_id,status,created) VALUES(?,?,?,?)",
            (user["id"], tid, "pending", now),
        )
    return {"ok": True, "status": "pending", "name": t_row["name"], "target": t_row["name"], "uid_num": 10000 + int(t_row["rowid"])}


@app.post("/api/friends/respond")
def respond_friend_request(data: FriendRespondInput, user=Depends(current_user)):
    target_q = (data.target or data.requester or "").strip()
    if data.accept is not None:
        act = "accept" if data.accept else "decline"
    else:
        act = data.action.strip().lower()
    now = time.time()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        t_row = _resolve_target_user(db, target_q)
        if not t_row:
            raise HTTPException(404, "Хэрэглэгч олдсонгүй")
        tid = t_row["id"]
        if act == "accept":
            db.execute(
                "INSERT OR REPLACE INTO friendships(user_id,friend_id,status,created) VALUES(?,?,?,?)",
                (tid, user["id"], "accepted", now),
            )
            db.execute(
                "INSERT OR REPLACE INTO friendships(user_id,friend_id,status,created) VALUES(?,?,?,?)",
                (user["id"], tid, "accepted", now),
            )
        else:
            db.execute(
                "DELETE FROM friendships WHERE (user_id=? AND friend_id=?) OR (user_id=? AND friend_id=?)",
                (user["id"], tid, tid, user["id"]),
            )
    return {"ok": True, "action": act}


@app.post("/api/users/block")
def block_or_unblock_user(data: BlockUserInput, user=Depends(current_user)):
    if data.block is not None:
        act = "block" if data.block else "unblock"
    else:
        act = data.action.strip().lower()
    now = time.time()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        t_row = _resolve_target_user(db, data.target)
        if not t_row:
            raise HTTPException(404, "Хэрэглэгч олдсонгүй")
        tid = t_row["id"]
        if tid == user["id"]:
            raise HTTPException(400, "Өөрийгөө блок хийх боломжгүй")
        if act == "unblock":
            db.execute("DELETE FROM blocks WHERE user_id=? AND blocked_id=?", (user["id"], tid))
        else:
            db.execute(
                "INSERT OR REPLACE INTO blocks(user_id,blocked_id,created) VALUES(?,?,?)",
                (user["id"], tid, now),
            )
            db.execute(
                "DELETE FROM friendships WHERE (user_id=? AND friend_id=?) OR (user_id=? AND friend_id=?)",
                (user["id"], tid, tid, user["id"]),
            )
    return {"ok": True, "action": act, "name": t_row["name"]}


@app.get("/api/social/sync")
def social_sync(user=Depends(current_user)):
    now = time.time()
    with database() as db:
        cleanup(db)
        me_row = db.execute("SELECT rowid AS rowid, * FROM users WHERE id=?", (user["id"],)).fetchone()
        me_rep = _compute_user_reputation(me_row, now, viewer_id=user["id"]) if me_row else {}
        friend_rows = db.execute(
            "SELECT u.rowid AS rowid, u.*, "
            "r.id AS room_id, r.name AS room_name, "
            "(SELECT count(*) FROM direct_messages dm WHERE dm.sender_id=u.id AND dm.receiver_id=? AND dm.is_read=0) AS unread "
            "FROM friendships f JOIN users u ON u.id=f.friend_id "
            "LEFT JOIN members m ON m.user_id=u.id "
            "LEFT JOIN rooms r ON r.id=m.room_id "
            "WHERE f.user_id=? AND f.status='accepted' "
            "ORDER BY unread DESC, (u.last_seen > ?) DESC, u.name ASC",
            (user["id"], user["id"], now - 35.0),
        ).fetchall()
        extra_dm_rows = db.execute(
            "SELECT u.rowid AS rowid, u.*, "
            "r.id AS room_id, r.name AS room_name, "
            "(SELECT count(*) FROM direct_messages dm WHERE dm.sender_id=u.id AND dm.receiver_id=? AND dm.is_read=0) AS unread "
            "FROM users u "
            "LEFT JOIN members m ON m.user_id=u.id "
            "LEFT JOIN rooms r ON r.id=m.room_id "
            "WHERE u.id IN (SELECT DISTINCT sender_id FROM direct_messages WHERE receiver_id=? AND is_read=0) "
            "AND u.id NOT IN (SELECT friend_id FROM friendships WHERE user_id=? AND status='accepted') "
            "AND u.id NOT IN (SELECT blocked_id FROM blocks WHERE user_id=?)",
            (user["id"], user["id"], user["id"], user["id"]),
        ).fetchall()
        friend_rows = list(extra_dm_rows) + list(friend_rows)
        req_in_rows = db.execute(
            "SELECT u.rowid AS rowid, u.name, f.created "
            "FROM friendships f JOIN users u ON u.id=f.user_id "
            "WHERE f.friend_id=? AND f.status='pending' ORDER BY f.created DESC",
            (user["id"],),
        ).fetchall()
        block_rows = db.execute(
            "SELECT u.rowid AS rowid, u.name "
            "FROM blocks b JOIN users u ON u.id=b.blocked_id "
            "WHERE b.user_id=? ORDER BY b.created DESC",
            (user["id"],),
        ).fetchall()
        invite_rows = db.execute(
            "SELECT i.id, i.room_id, r.name AS room_name, r.map_name, u.rowid AS sender_rowid, u.name AS from_name "
            "FROM room_invites i "
            "JOIN rooms r ON r.id=i.room_id "
            "JOIN users u ON u.id=i.sender_id "
            "WHERE i.receiver_id=? AND i.status='pending' AND i.created>? "
            "ORDER BY i.id DESC LIMIT 5",
            (user["id"], now - 180.0),
        ).fetchall()

    friends_out = []
    for f in friend_rows:
        f_rep = _compute_user_reputation(f, now, viewer_id=user["id"])
        friends_out.append({
            "uid_num": 10000 + int(f["rowid"]),
            "name": f["name"],
            "online": (now - float(f["last_seen"] or 0)) < 35.0,
            "room_id": f["room_id"] or "",
            "room_name": f["room_name"] or "",
            "unread": int(f["unread"] or 0),
            "badge_icon": f_rep["badge_icon"],
            "elo_text": f_rep["elo_text"],
        })
    reqs_out = [
        {
            "uid_num": 10000 + int(r["rowid"]),
            "name": r["name"],
        }
        for r in req_in_rows
    ]
    blocked_names = [b["name"] for b in block_rows]
    invites_out = [
        {
            "id": int(inv["id"]),
            "invite_id": int(inv["id"]),
            "room_id": inv["room_id"],
            "room_name": inv["room_name"],
            "map_name": inv["map_name"],
            "from_name": inv["from_name"],
            "from_user": inv["from_name"],
            "from_uid_num": 10000 + int(inv["sender_rowid"]),
        }
        for inv in invite_rows
    ]
    unread_dm_sum = sum(f["unread"] for f in friends_out)
    return {
        "ok": True,
        "uid_num": user["uid_num"],
        **me_rep,
        "me": {"name": user["name"], "uid_num": user["uid_num"], **me_rep},
        "unread_total": unread_dm_sum + len(reqs_out),
        "unread_dm": unread_dm_sum,
        "friends": friends_out,
        "incoming_requests": reqs_out,
        "requests_in": reqs_out,
        "blocked_users": blocked_names,
        "room_invites": invites_out,
        "invites": invites_out,
    }


@app.get("/api/dm/{target}")
def get_direct_messages(target: str, user=Depends(current_user)):
    with database() as db:
        t_row = _resolve_target_user(db, target)
        if not t_row:
            raise HTTPException(404, "Хэрэглэгч олдсонгүй")
        tid = t_row["id"]
        db.execute(
            "UPDATE direct_messages SET is_read=1 WHERE sender_id=? AND receiver_id=? AND is_read=0",
            (tid, user["id"]),
        )
        rows = db.execute(
            "SELECT dm.id, u.name AS sender, dm.text, dm.created "
            "FROM direct_messages dm JOIN users u ON u.id=dm.sender_id "
            "WHERE (dm.sender_id=? AND dm.receiver_id=?) OR (dm.sender_id=? AND dm.receiver_id=?) "
            "ORDER BY dm.id DESC LIMIT 80",
            (user["id"], tid, tid, user["id"]),
        ).fetchall()
    return {
        "ok": True,
        "friend_name": t_row["name"],
        "friend_uid_num": 10000 + int(t_row["rowid"]),
        "messages": [
            {
                "id": r["id"],
                "sender": r["sender"],
                "text": r["text"],
                "message": r["text"],
                "created_at": int(r["created"]),
                "time_str": time.strftime("%H:%M", time.localtime(r["created"])),
            }
            for r in reversed(rows)
        ],
    }


@app.post("/api/dm/{target}", status_code=201)
def send_direct_message(target: str, data: ChatInput, user=Depends(current_user)):
    msg_text = (data.text or data.message or "").strip()
    if not msg_text:
        raise HTTPException(400, "Empty message")
    now = time.time()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        t_row = _resolve_target_user(db, target)
        if not t_row:
            raise HTTPException(404, "Хэрэглэгч олдсонгүй")
        tid = t_row["id"]
        blocked = db.execute(
            "SELECT 1 FROM blocks WHERE (user_id=? AND blocked_id=?) OR (user_id=? AND blocked_id=?)",
            (user["id"], tid, tid, user["id"]),
        ).fetchone()
        if blocked:
            raise HTTPException(403, "Блок хийгдсэн хэрэглэгч рүү чат бичих боломжгүй.")
        cursor = db.execute(
            "INSERT INTO direct_messages(sender_id,receiver_id,text,is_read,created) VALUES(?,?,?,0,?)",
            (user["id"], tid, msg_text, now),
        )
        mid = cursor.lastrowid
    return {"ok": True, "id": mid}


@app.post("/api/rooms/{rid}/invite")
def invite_friend_to_room(rid: str, data: TargetUserInput, user=Depends(current_user)):
    now = time.time()
    wroom = w3gs_manager.get_room(rid)
    if wroom and wroom.phase != "LOBBY":
        raise HTTPException(403, "Тоглолт явагдаж байх үед болон Rejoin хүлээгдэж байх үед найзаа урих боломжгүй!")
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        require_member(db, rid, user)
        room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
        if not room:
            raise HTTPException(404, "Өрөө олдсонгүй")
        t_row = _resolve_target_user(db, data.target)
        if not t_row:
            raise HTTPException(404, "Хэрэглэгч олдсонгүй")
        tid = t_row["id"]
        if tid == user["id"]:
            raise HTTPException(400, "Өөрийгөө урих боломжгүй")
        db.execute(
            "DELETE FROM room_invites WHERE room_id=? AND receiver_id=? AND status='pending'",
            (rid, tid),
        )
        cursor = db.execute(
            "INSERT INTO room_invites(room_id,sender_id,receiver_id,status,created) VALUES(?,?,?,'pending',?)",
            (rid, user["id"], tid, now),
        )
        inv_id = cursor.lastrowid
        # Requirement #5: Also send room invite into 1-on-1 Direct Chat so friend can click Accept right in their private chat!
        dm_invite_text = f"📨 Таныг «{room['name']}» ({room['map_name']}) өрөөнд тоглохоор урилаа! [INVITE:{rid}:{inv_id}]"
        db.execute(
            "INSERT INTO direct_messages(sender_id,receiver_id,text,is_read,created) VALUES(?,?,?,0,?)",
            (user["id"], tid, dm_invite_text, now),
        )
    return {"ok": True, "invited": t_row["name"], "invite_id": inv_id}


@app.post("/api/invites/{inv_id}/respond")
def respond_room_invite(inv_id: int, data: InviteRespondInput, user=Depends(current_user)):
    if data.accept is not None:
        act = "accept" if data.accept else "decline"
    else:
        act = data.action.strip().lower()
    now = time.time()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        cleanup(db)
        inv = db.execute(
            "SELECT * FROM room_invites WHERE id=? AND receiver_id=?",
            (inv_id, user["id"]),
        ).fetchone()
        if not inv:
            raise HTTPException(404, "Урилга олдсонгүй эсвэл хугацаа дууссан байна")
        db.execute("UPDATE room_invites SET status=? WHERE id=?", (act, inv_id))
        if act != "accept":
            return {"ok": True, "action": act}
        rid = inv["room_id"]
        room = db.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
        if not room:
            raise HTTPException(404, "Урьсан өрөө хаагдсан байна")
        prev = db.execute("SELECT room_id FROM members WHERE user_id=?", (user["id"],)).fetchone()
        if prev and prev["room_id"] != rid:
            old_rid = prev["room_id"]
            _check_and_penalize_abandon_on_leave(db, old_rid, user)
            deleting_owner = db.execute("SELECT 1 FROM rooms WHERE id=? AND owner=?", (old_rid, user["id"])).fetchone()
            if deleting_owner:
                db.execute("DELETE FROM members WHERE room_id=?", (old_rid,))
                db.execute("DELETE FROM rooms WHERE id=?", (old_rid,))
                w3gs_manager.remove_room(old_rid)
            else:
                db.execute("DELETE FROM members WHERE room_id=? AND user_id=?", (old_rid, user["id"]))
        u_fresh = db.execute("SELECT rowid AS rowid, * FROM users WHERE id=?", (user["id"],)).fetchone()
        rep = _compute_user_reputation(u_fresh, now)
        if not (prev and prev["room_id"] == rid):
            count = db.execute("SELECT count(*) FROM members WHERE room_id=?", (rid,)).fetchone()[0]
            if count >= room["capacity"]:
                raise HTTPException(409, "Өрөө дүүрсэн байна")
            db.execute("INSERT INTO members VALUES(?,?)", (user["id"], rid))
            _emit_join_announcements(db, rid, u_fresh, rep, now, via_invite=True)
        map_meta = resolve_map_meta(db, room["map_name"])
        wroom = ensure_w3gs_room(rid, room, db=db)
        launch_sig = int(room["launch_signal"] if "launch_signal" in room.keys() else 0)
        is_owner = 1 if room["owner"] == user["id"] else 0
    return {
        "ok": True,
        "action": "accept",
        "room_id": rid,
        "room_name": room["name"],
        "map_name": room["map_name"],
        "is_owner": is_owner,
        "launch_signal": launch_sig,
        "w3gs_port": w3gs_manager.listen_port,
        "phase": wroom.phase,
        "host_counter": wroom.rejoin_counter if wroom.phase in ("WAITING", "LOADING") else wroom.host_counter,
        "entry_key": wroom.entry_key,
        "lan_ad_hex": wroom.get_lan_advertisement(6210).hex(),
        "id": map_meta.get("id", "lod_sync_25"),
        "filename": map_meta["filename"],
        "sha256": map_meta["sha256"],
        "map": {
            "id": map_meta.get("id", "lod_sync_25"),
            "filename": map_meta["filename"],
            "map_path": map_meta["map_path"],
            "file_size": map_meta["file_size"],
            "sha256": map_meta["sha256"],
            "download_url": f"/api/maps/{map_meta.get('id', map_meta['filename'])}/download",
        },
    }

