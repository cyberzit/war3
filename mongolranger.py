"""MongolRanger — GameRanger-Style Warcraft III Gaming Platform.

Complete client application with:
1. User Authentication (Login / Register / Password Recovery)
2. GameRanger-style Online Lobby (Rooms, Join, Host, Chat)
3. Interactive sRn-style WarKey Inventory Remapper (click slot → press key → assigned)
4. 1-Click Crash Recovery
5. Built-in Auto-Patcher for friends' War3
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.config import load_config, save_config, detect_warcraft_directory
from core.warkey import AegisWarKey, VK_NUMPAD7, VK_NUMPAD8, VK_NUMPAD4, VK_NUMPAD5, VK_NUMPAD1, VK_NUMPAD2

# ── User database (local JSON, will migrate to VPS later) ──────────────
USER_DB = ROOT / "data" / "users.json"
SETTINGS_FILE = ROOT / "data" / "settings.json"

GAME_DIR = detect_warcraft_directory()
MAPS_DIR = GAME_DIR / "Maps" / "Download"
SAVE_DIR = GAME_DIR / "Save" / "Multiplayer"

# Color palette
BG_DARK = "#0a0e17"
BG_CARD = "#111827"
BG_INPUT = "#1e293b"
FG_WHITE = "#f1f5f9"
FG_DIM = "#94a3b8"
FG_BRAND = "#3b82f6"
FG_GREEN = "#10b981"
FG_AMBER = "#f59e0b"
FG_RED = "#ef4444"
BTN_PRIMARY = "#2563eb"
BTN_SUCCESS = "#059669"
BTN_DANGER = "#dc2626"

# Inventory slot names (War3 numpad targets)
SLOT_TARGETS = [
    ("Slot 1", VK_NUMPAD7),
    ("Slot 2", VK_NUMPAD8),
    ("Slot 3", VK_NUMPAD4),
    ("Slot 4", VK_NUMPAD5),
    ("Slot 5", VK_NUMPAD1),
    ("Slot 6", VK_NUMPAD2),
]

# ═══════════════════════════════════════════════════════════════════════════
#  USER DATABASE (local file, will move to VPS API later)
# ═══════════════════════════════════════════════════════════════════════════

def _ensure_data_dir():
    USER_DB.parent.mkdir(parents=True, exist_ok=True)


def _load_users() -> dict:
    _ensure_data_dir()
    if USER_DB.is_file():
        try:
            return json.loads(USER_DB.read_text("utf-8"))
        except Exception:
            pass
    return {}


def _save_users(users: dict):
    _ensure_data_dir()
    USER_DB.write_text(json.dumps(users, indent=2, ensure_ascii=False), "utf-8")


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def register_user(username: str, password: str, recovery_q: str, recovery_a: str) -> tuple[bool, str]:
    """Register a new user. Returns (success, message)."""
    username = username.strip()
    if not username or len(username) < 2:
        return False, "Хэрэглэгчийн нэр хамгийн багадаа 2 тэмдэгт байна."
    if len(password) < 4:
        return False, "Нууц үг хамгийн багадаа 4 тэмдэгт байна."
    if not recovery_q.strip() or not recovery_a.strip():
        return False, "Нууц үг сэргээх асуулт, хариултыг бөглөнө үү."

    users = _load_users()
    key = username.lower()
    if key in users:
        return False, f"'{username}' нэр аль хэдийн бүртгэгдсэн байна."

    users[key] = {
        "username": username,
        "password": _hash_pw(password),
        "recovery_q": recovery_q.strip(),
        "recovery_a": _hash_pw(recovery_a.strip().lower()),
        "created": time.time(),
    }
    _save_users(users)
    return True, "Амжилттай бүртгэгдлээ!"


def login_user(username: str, password: str) -> tuple[bool, str]:
    """Validate login. Returns (success, message)."""
    users = _load_users()
    key = username.strip().lower()
    if key not in users:
        return False, "Хэрэглэгч олдсонгүй."
    if users[key]["password"] != _hash_pw(password):
        return False, "Нууц үг буруу байна."
    return True, users[key]["username"]


def get_recovery_question(username: str) -> str | None:
    users = _load_users()
    key = username.strip().lower()
    if key in users:
        return users[key].get("recovery_q")
    return None


def reset_password(username: str, recovery_answer: str, new_password: str) -> tuple[bool, str]:
    users = _load_users()
    key = username.strip().lower()
    if key not in users:
        return False, "Хэрэглэгч олдсонгүй."
    if users[key]["recovery_a"] != _hash_pw(recovery_answer.strip().lower()):
        return False, "Хариулт буруу байна."
    if len(new_password) < 4:
        return False, "Шинэ нууц үг хамгийн багадаа 4 тэмдэгт байна."
    users[key]["password"] = _hash_pw(new_password)
    _save_users(users)
    return True, "Нууц үг амжилттай солигдлоо!"


# ═══════════════════════════════════════════════════════════════════════════
#  SETTINGS PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════

def load_settings() -> dict:
    _ensure_data_dir()
    if SETTINGS_FILE.is_file():
        try:
            return json.loads(SETTINGS_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def save_settings(data: dict):
    _ensure_data_dir()
    existing = load_settings()
    existing.update(data)
    SETTINGS_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), "utf-8")


# Key name helper
VK_NAMES = {
    0x20: "Space", 0x09: "Tab", 0x1B: "Esc", 0x0D: "Enter",
    0x08: "Backspace", 0x2E: "Delete", 0x24: "Home", 0x23: "End",
    0x21: "PgUp", 0x22: "PgDn", 0x25: "←", 0x26: "↑", 0x27: "→", 0x28: "↓",
    0x70: "F1", 0x71: "F2", 0x72: "F3", 0x73: "F4", 0x74: "F5",
    0x75: "F6", 0x76: "F7", 0x77: "F8", 0x78: "F9", 0x79: "F10",
    0x7A: "F11", 0x7B: "F12",
    0xA0: "LShift", 0xA1: "RShift", 0xA2: "LCtrl", 0xA3: "RCtrl",
    0xA4: "LAlt", 0xA5: "RAlt",
    0xC0: "`",  0xBD: "-", 0xBB: "=",
    0xDB: "[", 0xDD: "]", 0xDC: "\\", 0xBA: ";", 0xDE: "'",
    0xBC: ",", 0xBE: ".", 0xBF: "/",
}

def vk_to_name(vk: int) -> str:
    if vk in VK_NAMES:
        return VK_NAMES[vk]
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num{vk - 0x60}"
    return f"0x{vk:02X}"


# ═══════════════════════════════════════════════════════════════════════════
#  LOGIN / REGISTER WINDOW
# ═══════════════════════════════════════════════════════════════════════════

class LoginWindow(tk.Tk):
    """First screen: User must login or register before accessing the platform."""

    def __init__(self):
        super().__init__()
        self.title("MongolRanger — Нэвтрэх")
        self.geometry("460x520")
        self.resizable(False, False)
        self.configure(bg=BG_DARK)
        self.result_username = None

        # Check auto-login
        settings = load_settings()
        saved_user = settings.get("last_user")
        if saved_user:
            users = _load_users()
            if saved_user.lower() in users:
                self.result_username = users[saved_user.lower()]["username"]
                self.destroy()
                return

        self._build_login_screen()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self.result_username = None
        self.destroy()

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def _build_login_screen(self):
        self._clear()
        self.title("MongolRanger — Нэвтрэх")

        # Logo area
        tk.Label(self, text="🐎", font=("Segoe UI Emoji", 42), bg=BG_DARK, fg=FG_BRAND).pack(pady=(30, 0))
        tk.Label(self, text="MONGOLRANGER", font=("Segoe UI", 18, "bold"),
                 bg=BG_DARK, fg=FG_WHITE).pack()
        tk.Label(self, text="Warcraft III TFT 1.26a • GameRanger-Style Platform",
                 font=("Segoe UI", 8), bg=BG_DARK, fg=FG_DIM).pack(pady=(0, 20))

        # Card
        card = tk.Frame(self, bg=BG_CARD, padx=30, pady=24)
        card.pack(fill="x", padx=40)

        tk.Label(card, text="Нэвтрэх", font=("Segoe UI", 13, "bold"),
                 bg=BG_CARD, fg=FG_WHITE).pack(anchor="w")

        tk.Label(card, text="Хэрэглэгчийн нэр:", font=("Segoe UI", 9),
                 bg=BG_CARD, fg=FG_DIM).pack(anchor="w", pady=(12, 2))
        self.entry_login_user = tk.Entry(card, font=("Segoe UI", 11), bg=BG_INPUT, fg=FG_WHITE,
                                         insertbackground=FG_WHITE, relief="flat")
        self.entry_login_user.pack(fill="x", ipady=5)
        self.entry_login_user.focus_set()

        tk.Label(card, text="Нууц үг:", font=("Segoe UI", 9),
                 bg=BG_CARD, fg=FG_DIM).pack(anchor="w", pady=(10, 2))
        self.entry_login_pass = tk.Entry(card, font=("Segoe UI", 11), bg=BG_INPUT, fg=FG_WHITE,
                                         insertbackground=FG_WHITE, relief="flat", show="●")
        self.entry_login_pass.pack(fill="x", ipady=5)
        self.entry_login_pass.bind("<Return>", lambda e: self._do_login())

        self.lbl_login_msg = tk.Label(card, text="", font=("Segoe UI", 9), bg=BG_CARD, fg=FG_RED)
        self.lbl_login_msg.pack(anchor="w", pady=(6, 0))

        btn_login = tk.Button(card, text="НЭВТРЭХ", font=("Segoe UI", 10, "bold"),
                              bg=BTN_PRIMARY, fg=FG_WHITE, activebackground="#1d4ed8",
                              relief="flat", pady=6, cursor="hand2", command=self._do_login)
        btn_login.pack(fill="x", pady=(14, 6))

        # Bottom links
        link_frame = tk.Frame(card, bg=BG_CARD)
        link_frame.pack(fill="x")

        btn_register = tk.Label(link_frame, text="Бүртгүүлэх", font=("Segoe UI", 9, "underline"),
                                bg=BG_CARD, fg=FG_BRAND, cursor="hand2")
        btn_register.pack(side="left")
        btn_register.bind("<Button-1>", lambda e: self._build_register_screen())

        btn_forgot = tk.Label(link_frame, text="Нууц үг мартсан?", font=("Segoe UI", 9, "underline"),
                              bg=BG_CARD, fg=FG_AMBER, cursor="hand2")
        btn_forgot.pack(side="right")
        btn_forgot.bind("<Button-1>", lambda e: self._build_recovery_screen())

    def _do_login(self):
        username = self.entry_login_user.get().strip()
        password = self.entry_login_pass.get()
        if not username or not password:
            self.lbl_login_msg.config(text="Бүх талбарыг бөглөнө үү.", fg=FG_RED)
            return
        ok, msg = login_user(username, password)
        if ok:
            self.result_username = msg  # msg is the original-case username
            save_settings({"last_user": username.lower()})
            self.destroy()
        else:
            self.lbl_login_msg.config(text=msg, fg=FG_RED)

    def _build_register_screen(self):
        self._clear()
        self.title("MongolRanger — Бүртгүүлэх")

        tk.Label(self, text="🐎", font=("Segoe UI Emoji", 32), bg=BG_DARK, fg=FG_BRAND).pack(pady=(20, 0))
        tk.Label(self, text="ШИНЭ БҮРТГЭЛ ҮҮСГЭХ", font=("Segoe UI", 14, "bold"),
                 bg=BG_DARK, fg=FG_WHITE).pack(pady=(0, 14))

        card = tk.Frame(self, bg=BG_CARD, padx=28, pady=18)
        card.pack(fill="x", padx=40)

        fields = [
            ("Хэрэглэгчийн нэр:", False),
            ("Нууц үг:", True),
            ("Нууц үг давтах:", True),
            ("Нууц үг сэргээх асуулт:", False),
            ("Хариулт:", False),
        ]
        self._reg_entries = []
        for label, is_pw in fields:
            tk.Label(card, text=label, font=("Segoe UI", 9), bg=BG_CARD, fg=FG_DIM).pack(anchor="w", pady=(6, 1))
            e = tk.Entry(card, font=("Segoe UI", 10), bg=BG_INPUT, fg=FG_WHITE,
                         insertbackground=FG_WHITE, relief="flat", show="●" if is_pw else "")
            e.pack(fill="x", ipady=4)
            self._reg_entries.append(e)

        self._reg_entries[0].focus_set()

        self.lbl_reg_msg = tk.Label(card, text="", font=("Segoe UI", 9), bg=BG_CARD, fg=FG_RED)
        self.lbl_reg_msg.pack(anchor="w", pady=(6, 0))

        tk.Button(card, text="БҮРТГҮҮЛЭХ", font=("Segoe UI", 10, "bold"),
                  bg=BTN_SUCCESS, fg=FG_WHITE, relief="flat", pady=6,
                  cursor="hand2", command=self._do_register).pack(fill="x", pady=(12, 6))

        btn_back = tk.Label(card, text="← Нэвтрэх хуудас руу буцах", font=("Segoe UI", 9, "underline"),
                            bg=BG_CARD, fg=FG_BRAND, cursor="hand2")
        btn_back.pack(anchor="w")
        btn_back.bind("<Button-1>", lambda e: self._build_login_screen())

    def _do_register(self):
        vals = [e.get() for e in self._reg_entries]
        username, pw, pw2, q, a = vals
        if pw != pw2:
            self.lbl_reg_msg.config(text="Нууц үг таарахгүй байна.", fg=FG_RED)
            return
        ok, msg = register_user(username, pw, q, a)
        if ok:
            self.lbl_reg_msg.config(text=msg, fg=FG_GREEN)
            self.after(1200, self._build_login_screen)
        else:
            self.lbl_reg_msg.config(text=msg, fg=FG_RED)

    def _build_recovery_screen(self):
        self._clear()
        self.title("MongolRanger — Нууц Үг Сэргээх")

        tk.Label(self, text="🔑", font=("Segoe UI Emoji", 32), bg=BG_DARK).pack(pady=(30, 0))
        tk.Label(self, text="НУУЦ ҮГ СЭРГЭЭХ", font=("Segoe UI", 14, "bold"),
                 bg=BG_DARK, fg=FG_WHITE).pack(pady=(0, 14))

        card = tk.Frame(self, bg=BG_CARD, padx=28, pady=18)
        card.pack(fill="x", padx=40)

        tk.Label(card, text="Хэрэглэгчийн нэр:", font=("Segoe UI", 9),
                 bg=BG_CARD, fg=FG_DIM).pack(anchor="w", pady=(4, 1))
        self.entry_rec_user = tk.Entry(card, font=("Segoe UI", 10), bg=BG_INPUT, fg=FG_WHITE,
                                       insertbackground=FG_WHITE, relief="flat")
        self.entry_rec_user.pack(fill="x", ipady=4)
        self.entry_rec_user.focus_set()

        self.lbl_rec_q = tk.Label(card, text="", font=("Segoe UI", 9, "bold"),
                                  bg=BG_CARD, fg=FG_AMBER, wraplength=340, justify="left")
        self.lbl_rec_q.pack(anchor="w", pady=(10, 2))

        tk.Label(card, text="Хариулт:", font=("Segoe UI", 9), bg=BG_CARD, fg=FG_DIM).pack(anchor="w", pady=(4, 1))
        self.entry_rec_ans = tk.Entry(card, font=("Segoe UI", 10), bg=BG_INPUT, fg=FG_WHITE,
                                      insertbackground=FG_WHITE, relief="flat")
        self.entry_rec_ans.pack(fill="x", ipady=4)

        tk.Label(card, text="Шинэ нууц үг:", font=("Segoe UI", 9), bg=BG_CARD, fg=FG_DIM).pack(anchor="w", pady=(8, 1))
        self.entry_rec_newpw = tk.Entry(card, font=("Segoe UI", 10), bg=BG_INPUT, fg=FG_WHITE,
                                        insertbackground=FG_WHITE, relief="flat", show="●")
        self.entry_rec_newpw.pack(fill="x", ipady=4)

        self.lbl_rec_msg = tk.Label(card, text="", font=("Segoe UI", 9), bg=BG_CARD, fg=FG_RED)
        self.lbl_rec_msg.pack(anchor="w", pady=(6, 0))

        btn_frame = tk.Frame(card, bg=BG_CARD)
        btn_frame.pack(fill="x", pady=(10, 6))

        tk.Button(btn_frame, text="Асуулт Харах", font=("Segoe UI", 9),
                  bg="#374151", fg=FG_WHITE, relief="flat", padx=10, pady=4,
                  cursor="hand2", command=self._show_question).pack(side="left", padx=(0, 6))

        tk.Button(btn_frame, text="НУУЦ ҮГ СОЛИХ", font=("Segoe UI", 10, "bold"),
                  bg=BTN_PRIMARY, fg=FG_WHITE, relief="flat", padx=14, pady=4,
                  cursor="hand2", command=self._do_reset).pack(side="left")

        btn_back = tk.Label(card, text="← Нэвтрэх хуудас руу буцах", font=("Segoe UI", 9, "underline"),
                            bg=BG_CARD, fg=FG_BRAND, cursor="hand2")
        btn_back.pack(anchor="w", pady=(8, 0))
        btn_back.bind("<Button-1>", lambda e: self._build_login_screen())

    def _show_question(self):
        username = self.entry_rec_user.get().strip()
        q = get_recovery_question(username)
        if q:
            self.lbl_rec_q.config(text=f"Асуулт: {q}")
        else:
            self.lbl_rec_msg.config(text="Хэрэглэгч олдсонгүй.", fg=FG_RED)

    def _do_reset(self):
        username = self.entry_rec_user.get().strip()
        answer = self.entry_rec_ans.get()
        new_pw = self.entry_rec_newpw.get()
        ok, msg = reset_password(username, answer, new_pw)
        if ok:
            self.lbl_rec_msg.config(text=msg, fg=FG_GREEN)
            self.after(1500, self._build_login_screen)
        else:
            self.lbl_rec_msg.config(text=msg, fg=FG_RED)


# ═══════════════════════════════════════════════════════════════════════════
#  INTERACTIVE WARKEY WIDGET (sRn Warkey Style)
# ═══════════════════════════════════════════════════════════════════════════

SKILL_SLOTS = [
    ("Skill 1", 0x51),  # Q
    ("Skill 2", 0x57),  # W
    ("Skill 3", 0x45),  # E
    ("Skill 4", 0x52),  # R
    ("Skill 5", 0x44),  # D
    ("Skill 6", 0x46),  # F
    ("Skill 7", 0x47),  # G
    ("Skill 8", 0x54),  # T
]

class WarKeyGrid(tk.Frame):
    """Ultra-clean, modern, zero-clutter WarKey: 6 Inventory slots + 8 Skill slots.
    Always active in Warcraft III / DotA. Click any slot to assign key; right-click to clear.
    """

    def __init__(self, parent, warkey_engine: AegisWarKey, on_mapping_changed=None, **kwargs):
        super().__init__(parent, bg=BG_DARK, **kwargs)
        self.warkey = warkey_engine
        self.on_mapping_changed = on_mapping_changed
        self.inv_buttons: list[tk.Button] = []
        self.skill_buttons: list[tk.Button] = []
        self.listening: tuple[str, int] | None = None

        self.inv_slots: dict[int, int | None] = {i: None for i in range(6)}
        self.skill_slots: dict[int, int | None] = {i: None for i in range(8)}

        self._load_saved_mappings()
        self._build()

        # Ensure engine is active
        if not self.warkey.enabled:
            self.warkey.start()

    def _load_saved_mappings(self):
        settings = load_settings()

        # 1. Inventory mapping: EMPTY BY DEFAULT! Only load what user explicitly configured
        saved_inv = settings.get("warkey_inv_slots")
        if saved_inv and isinstance(saved_inv, dict):
            self.inv_slots = {int(k): int(v) if v is not None else None for k, v in saved_inv.items()}
        else:
            self.inv_slots = {i: None for i in range(6)}

        # 2. Skill mapping: EMPTY BY DEFAULT! Only load what user explicitly configured
        saved_skills = settings.get("warkey_skill_slots")
        if saved_skills and isinstance(saved_skills, dict):
            self.skill_slots = {int(k): int(v) if v is not None else None for k, v in saved_skills.items()}
        else:
            self.skill_slots = {i: None for i in range(8)}

        self._sync_engine_mapping()

    def _sync_engine_mapping(self):
        inv_map = {}
        for idx, vk in self.inv_slots.items():
            if vk is not None:
                target_numpad = SLOT_TARGETS[idx][1]
                inv_map[vk] = target_numpad
        self.warkey.inv_mapping = inv_map
        self.warkey.mapping = inv_map

        skill_map = {}
        for idx, src_vk in self.skill_slots.items():
            if src_vk is not None:
                target_skill_vk = SKILL_SLOTS[idx][1]
                skill_map[src_vk] = target_skill_vk
        self.warkey.skill_mapping = skill_map

        save_settings({
            "warkey_inv_slots": {str(k): v for k, v in self.inv_slots.items()},
            "warkey_skill_slots": {str(k): v for k, v in self.skill_slots.items()},
        })
        if self.on_mapping_changed:
            self.on_mapping_changed(inv_map)

    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        self.inv_buttons.clear()
        self.skill_buttons.clear()

        # Modern card frame
        card = tk.Frame(self, bg=BG_CARD, padx=28, pady=24, relief="ridge", bd=1)
        card.pack(anchor="center")

        # Top status line: clean and reassuring
        top_info = tk.Frame(card, bg=BG_CARD)
        top_info.pack(fill="x", pady=(0, 16))

        self.lbl_status = tk.Label(top_info, text="WARKEY БЭЛЭН", font=("Segoe UI", 11, "bold"),
                                   bg=BG_CARD, fg=FG_GREEN)
        self.lbl_status.pack(side="left")
        tk.Label(top_info, text="Warcraft III / DotA дээр автоматаар шууд идэвхжинэ",
                 font=("Segoe UI", 9), bg=BG_CARD, fg=FG_DIM).pack(side="right")

        # Grid container (side by side)
        grid_row = tk.Frame(card, bg=BG_CARD)
        grid_row.pack()

        # ══════════════ 1. INVENTORY SECTION ══════════════
        inv_panel = tk.Frame(grid_row, bg=BG_CARD)
        inv_panel.pack(side="left", padx=(0, 28), anchor="n")

        tk.Label(inv_panel, text="INVENTORY", font=("Segoe UI", 12, "bold"),
                 bg=BG_CARD, fg="#38bdf8").pack(anchor="w", pady=(0, 10))

        inv_grid = tk.Frame(inv_panel, bg=BG_CARD)
        inv_grid.pack()

        for idx in range(6):
            r, c = divmod(idx, 2)
            vk = self.inv_slots.get(idx)
            name = vk_to_name(vk) if vk else "—"

            btn = tk.Button(inv_grid, text=name, font=("Segoe UI", 12, "bold"),
                            width=7, height=2, bg=BG_INPUT, fg=FG_WHITE if vk else FG_DIM,
                            activebackground="#334155", activeforeground=FG_WHITE,
                            relief="flat", bd=1, cursor="hand2",
                            command=lambda i=idx: self._start_listen("inv", i))
            btn.bind("<Button-3>", lambda e, i=idx: self._clear_slot("inv", i))
            btn.bind("<BackSpace>", lambda e, i=idx: self._clear_slot("inv", i))
            btn.bind("<Delete>", lambda e, i=idx: self._clear_slot("inv", i))
            btn.grid(row=r, column=c, padx=5, pady=5)
            self.inv_buttons.append(btn)

        # Subtle divider line
        divider = tk.Frame(grid_row, bg="#334155", width=1)
        divider.pack(side="left", fill="y", padx=(0, 28))

        # ══════════════ 2. SKILLS SECTION ══════════════
        skill_panel = tk.Frame(grid_row, bg=BG_CARD)
        skill_panel.pack(side="left", anchor="n")

        tk.Label(skill_panel, text="SKILLS (DotA Abilities)", font=("Segoe UI", 12, "bold"),
                 bg=BG_CARD, fg="#fbbf24").pack(anchor="w", pady=(0, 10))

        skill_grid = tk.Frame(skill_panel, bg=BG_CARD)
        skill_grid.pack()

        for idx in range(8):
            r, c = divmod(idx, 4)
            vk = self.skill_slots.get(idx)
            name = vk_to_name(vk) if vk else "—"

            btn = tk.Button(skill_grid, text=name, font=("Segoe UI", 12, "bold"),
                            width=7, height=2, bg=BG_INPUT, fg=FG_WHITE if vk else FG_DIM,
                            activebackground="#334155", activeforeground=FG_WHITE,
                            relief="flat", bd=1, cursor="hand2",
                            command=lambda i=idx: self._start_listen("skill", i))
            btn.bind("<Button-3>", lambda e, i=idx: self._clear_slot("skill", i))
            btn.bind("<BackSpace>", lambda e, i=idx: self._clear_slot("skill", i))
            btn.bind("<Delete>", lambda e, i=idx: self._clear_slot("skill", i))
            btn.grid(row=r, column=c, padx=5, pady=5)
            self.skill_buttons.append(btn)

        # ══════════════ BOTTOM HINT ══════════════
        hint_frame = tk.Frame(card, bg="#0b0f19", padx=12, pady=8, relief="flat")
        hint_frame.pack(fill="x", pady=(20, 0))

        self.lbl_hint = tk.Label(
            hint_frame,
            text="💡 Нүдэн дээр товшоод товч дарж тохируулна.  |  Арилгах бол Backspace эсвэл хулганы баруун товч дарна.",
            font=("Segoe UI", 9), bg="#0b0f19", fg=FG_DIM
        )
        self.lbl_hint.pack(anchor="center")
        self.lbl_hint.configure(wraplength=680)
        if not getattr(self, "_status_timer", None):
            self._refresh_status()

    def _refresh_status(self):
        if self.warkey.last_error:
            self.lbl_status.config(text="WARKEY: ШАЛГАХ ШААРДЛАГАТАЙ", fg=FG_AMBER)
            self.lbl_hint.config(text=self.warkey.last_error, fg=FG_AMBER)
        elif not self.warkey.hook_id:
            self.lbl_status.config(text="WARKEY ЭХЛЭЭГҮЙ", fg=FG_AMBER)
        else:
            self.lbl_status.config(text="WARKEY БЭЛЭН", fg=FG_GREEN)
        self._status_timer = self.after(500, self._refresh_status)

    def _start_listen(self, slot_type: str, idx: int):
        self.listening = (slot_type, idx)
        btn = self.inv_buttons[idx] if slot_type == "inv" else self.skill_buttons[idx]
        btn.config(text="...", bg="#b45309", fg=FG_WHITE)

        name_str = f"Inventory Slot {idx + 1}" if slot_type == "inv" else f"Skill Slot {idx + 1}"
        self.lbl_hint.config(text=f"▶ {name_str} — Товчоо дарна уу (Арилгах бол Backspace)...", fg=FG_AMBER)

        self.winfo_toplevel().bind("<Key>", self._on_key_captured)

    def _on_key_captured(self, event):
        if not self.listening:
            return
        slot_type, idx = self.listening
        self.listening = None
        try:
            self.winfo_toplevel().unbind("<Key>")
        except Exception:
            pass

        vk = event.keycode

        # 1. BackSpace or Delete -> Clear/Delete the slot!
        if vk in (0x08, 0x2E) or event.keysym in ("BackSpace", "Delete"):
            self._clear_slot(slot_type, idx)
            return

        # 2. Escape -> Cancel listen mode without changing
        if vk == 0x1B or event.keysym == "Escape":
            curr_vk = self.inv_slots.get(idx) if slot_type == "inv" else self.skill_slots.get(idx)
            btn = self.inv_buttons[idx] if slot_type == "inv" else self.skill_buttons[idx]
            btn.config(text=vk_to_name(curr_vk) if curr_vk else "—", bg=BG_INPUT, fg=FG_WHITE if curr_vk else FG_DIM)
            self.lbl_hint.config(text="Тохиргоог цуцаллаа.", fg=FG_DIM)
            return

        name = vk_to_name(vk)

        if slot_type == "inv":
            self.inv_slots[idx] = vk
            btn = self.inv_buttons[idx]
            btn.config(text=name, bg=BG_INPUT, fg=FG_WHITE)
            self.lbl_hint.config(text=f"✓ Inventory Slot {idx + 1} → '{name}' амжилттай тохируулагдлаа", fg=FG_GREEN)
        else:
            self.skill_slots[idx] = vk
            btn = self.skill_buttons[idx]
            btn.config(text=name, bg=BG_INPUT, fg=FG_WHITE)
            self.lbl_hint.config(text=f"✓ Skill Slot {idx + 1} → '{name}' амжилттай тохируулагдлаа", fg=FG_GREEN)

        self._sync_engine_mapping()

    def _clear_slot(self, slot_type: str, idx: int):
        if self.listening:
            self.listening = None
            try:
                self.winfo_toplevel().unbind("<Key>")
            except Exception:
                pass
        if slot_type == "inv":
            self.inv_slots[idx] = None
            self.inv_buttons[idx].config(text="—", bg=BG_INPUT, fg=FG_DIM)
        else:
            self.skill_slots[idx] = None
            self.skill_buttons[idx].config(text="—", bg=BG_INPUT, fg=FG_DIM)
        self._sync_engine_mapping()
        self.lbl_hint.config(text="✓ Сонгосон товчийг амжилттай арилгалаа (Backspace / Clear).", fg=FG_GREEN)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════

class MongolRangerApp(tk.Tk):
    """Main window after login — GameRanger-style platform."""

    def __init__(self, username: str):
        super().__init__()
        self.username = username
        self.title(f"MongolRanger — {username}")
        self.geometry("1020x700")
        self.minsize(900, 620)
        self.configure(bg=BG_DARK)

        # Core engines
        self.warkey = AegisWarKey()
        self._load_warkey_mapping()

        # Styles
        self._init_styles()

        # Build UI
        self._build_header()
        self._build_tabs()
        self._build_footer()

        # Foreground
        self.lift()
        self.attributes("-topmost", True)
        self.after(600, lambda: self.attributes("-topmost", False))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_warkey_mapping(self):
        settings = load_settings()

        # 1. Inventory mapping
        saved_inv = settings.get("warkey_inv_slots")
        if saved_inv and isinstance(saved_inv, dict):
            inv_map = {}
            for k, v in saved_inv.items():
                if v is not None:
                    idx = int(k)
                    if idx < len(SLOT_TARGETS):
                        inv_map[int(v)] = SLOT_TARGETS[idx][1]
            self.warkey.inv_mapping = inv_map
            self.warkey.mapping = inv_map

        # 2. Skill mapping
        saved_skills = settings.get("warkey_skill_slots")
        if saved_skills and isinstance(saved_skills, dict):
            skill_map = {}
            for k, v in saved_skills.items():
                if v is not None:
                    idx = int(k)
                    if idx < len(SKILL_SLOTS):
                        skill_map[int(v)] = SKILL_SLOTS[idx][1]
            self.warkey.skill_mapping = skill_map

        # 3. Always active in background - ready for War3!
        self.warkey.start()

    def _init_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG_DARK, foreground=FG_WHITE)
        style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_CARD, foreground=FG_DIM,
                         padding=[14, 8], font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab",
                   background=[("selected", "#1e3a8a")],
                   foreground=[("selected", FG_WHITE)])
        style.configure("Treeview", background=BG_DARK, foreground=FG_WHITE,
                         fieldbackground=BG_DARK, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background=BG_CARD, foreground=FG_BRAND,
                         font=("Segoe UI", 9, "bold"))

    def _build_header(self):
        header = tk.Frame(self, bg=BG_CARD, height=56, padx=16, pady=8)
        header.pack(fill="x", side="top")

        left = tk.Frame(header, bg=BG_CARD)
        left.pack(side="left")

        tk.Label(left, text="🐎", font=("Segoe UI Emoji", 18), bg=BG_CARD, fg=FG_BRAND).pack(side="left", padx=(0, 8))

        title_col = tk.Frame(left, bg=BG_CARD)
        title_col.pack(side="left")
        tk.Label(title_col, text="MONGOLRANGER", font=("Segoe UI", 13, "bold"),
                 bg=BG_CARD, fg=FG_WHITE).pack(anchor="w")
        tk.Label(title_col, text="Warcraft III TFT 1.26a • DotA LoD Platform",
                 font=("Segoe UI", 8), bg=BG_CARD, fg=FG_DIM).pack(anchor="w")

        # Right: user info
        right = tk.Frame(header, bg=BG_CARD)
        right.pack(side="right")

        tk.Label(right, text=f"👤 {self.username}", font=("Segoe UI", 10, "bold"),
                 bg=BG_CARD, fg=FG_GREEN).pack(side="left", padx=(0, 12))

        btn_logout = tk.Button(right, text="Гарах", font=("Segoe UI", 8),
                               bg="#374151", fg=FG_DIM, relief="flat", padx=8, pady=2,
                               cursor="hand2", command=self._logout)
        btn_logout.pack(side="left")

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=8)

        # Tab 1: Online Lobby
        self.tab_lobby = tk.Frame(self.notebook, bg=BG_DARK, padx=10, pady=10)
        self.notebook.add(self.tab_lobby, text=" 🌐 Онлайн Лобби ")
        self._init_lobby_tab()

        # Tab 2: WarKey
        self.tab_warkey = tk.Frame(self.notebook, bg=BG_DARK, padx=10, pady=10)
        self.notebook.add(self.tab_warkey, text=" ⌨️ WarKey ")
        self._init_warkey_tab()

        # Tab 3: Settings
        self.tab_settings = tk.Frame(self.notebook, bg=BG_DARK, padx=10, pady=10)
        self.notebook.add(self.tab_settings, text=" ⚙️ Тохиргоо ")
        self._init_settings_tab()

    def _init_lobby_tab(self):
        panes = tk.Frame(self.tab_lobby, bg=BG_DARK)
        panes.pack(fill="both", expand=True)

        # ── Left: Room List ──
        col_rooms = tk.Frame(panes, bg=BG_CARD, padx=10, pady=10, relief="ridge", bd=1)
        col_rooms.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(col_rooms, text="НЭЭЛТТЭЙ ӨРӨӨНҮҮД",
                 font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=FG_BRAND).pack(anchor="w", pady=(0, 6))

        tree_frame = tk.Frame(col_rooms, bg=BG_CARD)
        tree_frame.pack(fill="both", expand=True)

        columns = ("name", "host", "map", "players", "status")
        self.tree_rooms = ttk.Treeview(tree_frame, columns=columns, show="headings", height=14)
        self.tree_rooms.heading("name", text="Өрөө")
        self.tree_rooms.heading("host", text="Хост")
        self.tree_rooms.heading("map", text="Газрын зураг")
        self.tree_rooms.heading("players", text="Тоглогч")
        self.tree_rooms.heading("status", text="Төлөв")
        self.tree_rooms.column("name", width=180)
        self.tree_rooms.column("host", width=90)
        self.tree_rooms.column("map", width=140)
        self.tree_rooms.column("players", width=60)
        self.tree_rooms.column("status", width=80)
        self.tree_rooms.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_rooms.yview)
        self.tree_rooms.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        btn_bar = tk.Frame(col_rooms, bg=BG_CARD)
        btn_bar.pack(fill="x", pady=(8, 0))

        tk.Button(btn_bar, text="🎮 Нэгдэх", font=("Segoe UI", 9, "bold"),
                  bg=BTN_PRIMARY, fg=FG_WHITE, relief="flat", padx=12, pady=4,
                  cursor="hand2", command=self._action_join_room).pack(side="left", padx=(0, 4))
        tk.Button(btn_bar, text="➕ Өрөө Үүсгэх", font=("Segoe UI", 9, "bold"),
                  bg=BTN_SUCCESS, fg=FG_WHITE, relief="flat", padx=12, pady=4,
                  cursor="hand2", command=self._action_create_room).pack(side="left", padx=(0, 4))
        tk.Button(btn_bar, text="🔄", font=("Segoe UI", 9),
                  bg="#374151", fg=FG_WHITE, relief="flat", padx=8, pady=4,
                  cursor="hand2", command=self._action_refresh).pack(side="left")

        # ── Right: Active Room / Chat ──
        col_active = tk.Frame(panes, bg=BG_CARD, padx=12, pady=12, relief="ridge", bd=1, width=300)
        col_active.pack(side="right", fill="both", padx=(6, 0))
        col_active.pack_propagate(False)

        tk.Label(col_active, text="ӨРӨӨНИЙ МЭДЭЭЛЭЛ",
                 font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=FG_DIM).pack(anchor="w")
        tk.Label(col_active, text="Зүүн талаас өрөө сонгоод нэгдэнэ үү.\nЭсвэл шинэ өрөө үүсгэнэ.",
                 font=("Segoe UI", 9), bg=BG_CARD, fg=FG_DIM, justify="left").pack(anchor="w", pady=(10, 0))

        # Chat area
        tk.Label(col_active, text="Чат:", font=("Segoe UI", 9, "bold"),
                 bg=BG_CARD, fg=FG_BRAND).pack(anchor="w", pady=(20, 4))
        self.txt_chat = tk.Text(col_active, font=("Consolas", 9), bg=BG_DARK, fg=FG_DIM,
                                relief="flat", height=10, state="disabled")
        self.txt_chat.pack(fill="both", expand=True, pady=(0, 6))

        chat_input = tk.Frame(col_active, bg=BG_CARD)
        chat_input.pack(fill="x")
        self.entry_chat = tk.Entry(chat_input, font=("Segoe UI", 9), bg=BG_INPUT, fg=FG_WHITE,
                                   insertbackground=FG_WHITE, relief="flat")
        self.entry_chat.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 4))
        self.entry_chat.bind("<Return>", lambda e: self._send_chat())
        tk.Button(chat_input, text="Илгээх", font=("Segoe UI", 8), bg="#374151", fg=FG_WHITE,
                  relief="flat", padx=8, pady=2, cursor="hand2",
                  command=self._send_chat).pack(side="right")

    def _init_warkey_tab(self):
        container = tk.Frame(self.tab_warkey, bg=BG_DARK)
        container.pack(fill="both", expand=True)

        self.warkey_grid = WarKeyGrid(container, self.warkey)
        self.warkey_grid.pack(anchor="center", pady=16)

    def _init_settings_tab(self):
        box = tk.Frame(self.tab_settings, bg=BG_CARD, padx=16, pady=16, relief="ridge", bd=1)
        box.pack(fill="both", expand=True)

        tk.Label(box, text="ТОХИРГОО", font=("Segoe UI", 11, "bold"),
                 bg=BG_CARD, fg=FG_BRAND).pack(anchor="w")

        # Game path
        tk.Label(box, text="Warcraft III хавтас:", font=("Segoe UI", 9, "bold"),
                 bg=BG_CARD, fg=FG_WHITE).pack(anchor="w", pady=(14, 2))
        path_row = tk.Frame(box, bg=BG_CARD)
        path_row.pack(fill="x")
        self.entry_path = tk.Entry(path_row, font=("Segoe UI", 9), bg=BG_INPUT, fg=FG_WHITE,
                                   insertbackground=FG_WHITE, relief="flat")
        self.entry_path.insert(0, str(GAME_DIR))
        self.entry_path.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))
        tk.Button(path_row, text="📁 Сонгох", font=("Segoe UI", 8),
                  bg="#374151", fg=FG_WHITE, relief="flat", padx=8, pady=2,
                  cursor="hand2", command=self._browse_path).pack(side="left")

        # 4GB Patch
        patch_card = tk.Frame(box, bg=BG_DARK, padx=12, pady=10, relief="ridge", bd=1)
        patch_card.pack(fill="x", pady=(14, 8))
        tk.Label(patch_card, text="4GB Patch & Авто-Тохиргоо", font=("Segoe UI", 9, "bold"),
                 bg=BG_DARK, fg=FG_WHITE).pack(anchor="w")
        tk.Label(patch_card, text="Найзын War3-ийг 1 товчоор тохируулна (4GB RAM, Compatibility, Cinematic Bypass).",
                 font=("Segoe UI", 8), bg=BG_DARK, fg=FG_DIM).pack(anchor="w", pady=(2, 6))
        tk.Button(patch_card, text="⚡ Авто-Тохиргоо Ажиллуулах", font=("Segoe UI", 9, "bold"),
                  bg=BTN_SUCCESS, fg=FG_WHITE, relief="flat", padx=12, pady=4,
                  cursor="hand2", command=self._run_patcher).pack(anchor="w")

        self.lbl_patch_result = tk.Label(box, text="", font=("Segoe UI", 9), bg=BG_CARD, fg=FG_GREEN)
        self.lbl_patch_result.pack(anchor="w", pady=(6, 0))

        # Account info
        acc_card = tk.Frame(box, bg=BG_DARK, padx=12, pady=10, relief="ridge", bd=1)
        acc_card.pack(fill="x", pady=(14, 8))
        tk.Label(acc_card, text=f"Бүртгэлтэй нэр: {self.username}", font=("Segoe UI", 9, "bold"),
                 bg=BG_DARK, fg=FG_GREEN).pack(anchor="w")
        tk.Button(acc_card, text="Нууц Үг Солих", font=("Segoe UI", 8),
                  bg="#374151", fg=FG_WHITE, relief="flat", padx=8, pady=2,
                  cursor="hand2", command=self._change_password).pack(anchor="w", pady=(6, 0))

    def _build_footer(self):
        footer = tk.Frame(self, bg=BG_DARK, padx=14, pady=5)
        footer.pack(fill="x", side="bottom")
        tk.Label(footer, text="MongolRanger v0.1 • Warcraft III TFT 1.26a",
                 font=("Segoe UI", 8), bg=BG_DARK, fg="#4b5563").pack(side="left")
        self.lbl_clock = tk.Label(footer, text="", font=("Segoe UI", 8), bg=BG_DARK, fg="#4b5563")
        self.lbl_clock.pack(side="right")
        self._tick_clock()

    def _tick_clock(self):
        self.lbl_clock.config(text=time.strftime("%Y-%m-%d %H:%M:%S"))
        self.after(1000, self._tick_clock)

    # ── Actions ──

    def _action_join_room(self):
        sel = self.tree_rooms.selection()
        if not sel:
            messagebox.showinfo("MongolRanger", "Өрөө сонгоно уу.")
            return
        messagebox.showinfo("MongolRanger", "Өрөөнд нэгдэж байна... (VPS тохируулсны дараа ажиллана)")

    def _action_create_room(self):
        messagebox.showinfo("MongolRanger", "Шинэ өрөө үүсгэх... (VPS тохируулсны дараа ажиллана)")

    def _action_refresh(self):
        self._chat_append("[System] Өрөөний жагсаалт шинэчлэгдлээ.")

    def _send_chat(self):
        msg = self.entry_chat.get().strip()
        if not msg:
            return
        self.entry_chat.delete(0, "end")
        self._chat_append(f"[{self.username}] {msg}")

    def _chat_append(self, text: str):
        self.txt_chat.config(state="normal")
        self.txt_chat.insert("end", f"{text}\n")
        self.txt_chat.see("end")
        self.txt_chat.config(state="disabled")

    def _browse_path(self):
        d = filedialog.askdirectory(title="Warcraft III хавтас сонгох")
        if d:
            p = Path(d)
            if (p / "war3.exe").is_file():
                self.entry_path.delete(0, "end")
                self.entry_path.insert(0, str(p))
                save_config({"game_path": str(p)})
            else:
                messagebox.showerror("Алдаа", "war3.exe олдсонгүй.")

    def _run_patcher(self):
        game_dir = Path(self.entry_path.get().strip())
        from core.war3_patcher import inspect_and_patch_war3
        res = inspect_and_patch_war3(game_dir, self.username)
        msgs = "\n".join(res["messages"])
        self.lbl_patch_result.config(text=msgs, fg=FG_GREEN if res["laa_4gb_active"] else FG_AMBER)

    def _change_password(self):
        messagebox.showinfo("MongolRanger", "Нууц үг солихдоо програмаас гараад 'Нууц үг мартсан?' дарна уу.")

    def _logout(self):
        save_settings({"last_user": ""})
        self.warkey.stop()
        self.destroy()
        # Restart login
        run_app()

    def _on_close(self):
        self.warkey.stop()
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def run_app():
    login = LoginWindow()
    login.mainloop()

    username = getattr(login, "result_username", None)
    if not username:
        return

    app = MongolRangerApp(username)
    app.mainloop()


if __name__ == "__main__":
    run_app()
