"""Aegis Gaming Platform - GameRanger Style All-in-One Warcraft III Host & Client.

Features:
1. 1-Click Host Room (DotA LoD).
2. 1-Click Instant Crash Recovery (Auto-hosts latest .w3z save with 0-sec catchup).
3. Universal LoD Map Converter (with -cam zoom command injection).
4. Built-in WarKey Inventory Remapper (Space, 1, 2, 3, 4, 5).
5. Silent Save-Sync Server (Port 6205) & Client Sync.
6. 1-Click Launch Warcraft III with 4GB Patch verification.
"""
import os
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import base64
from core.recovery_manager import AegisEngine, MAPS_DIR, SAVE_DIR, apply_4gb_patch
from core.save_sync import SaveSyncHost, get_latest_save, sync_save_from_host, ClientTunnel, get_host_status
from core.game_ranger_lobby import OnlineLobbyService
from core.warkey import AegisWarKey
from tools.map_converter import convert_map


class AegisApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Aegis - Warcraft III Gaming Platform & Recovery Hub")
        self.geometry("960x680")
        self.minsize(840, 600)
        self.configure(bg="#0b0f19")

        # Core Engines
        self.engine = AegisEngine()
        self.warkey = AegisWarKey()
        self.client_tunnel = None
        self.lobby_svc = OnlineLobbyService(player_name="ZEV")

        # Styles
        self._init_styles()

        # Build UI
        self._build_header()
        self._build_tabs()
        self._build_footer()

        # Wire Lobby Callbacks
        self.lobby_svc.on_room_state_changed = self._on_room_state_changed
        self.lobby_svc.on_game_start_signal = self._on_client_game_start
        self.lobby_svc.on_recovery_signal = self._on_client_recovery
        threading.Thread(target=self._start_lobby_service, daemon=True).start()

        # Bring window to foreground
        self.lift()
        self.attributes('-topmost', True)
        self.after(500, lambda: self.attributes('-topmost', False))

        # Protocol cleanup on close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _init_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#0b0f19", foreground="#e5e7eb")
        style.configure("TNotebook", background="#0b0f19", borderwidth=0)
        style.configure("TNotebook.Tab", background="#111827", foreground="#9ca3af",
                        padding=[14, 8], font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", "#1e3a8a")],
                  foreground=[("selected", "#ffffff")])
        style.configure("Card.TFrame", background="#111827", relief="flat")
        style.configure("Inner.TFrame", background="#0b0f19", relief="flat")

    def _build_header(self):
        header = tk.Frame(self, bg="#111827", height=60, padx=16, pady=10)
        header.pack(fill="x", side="top")

        title_box = tk.Frame(header, bg="#111827")
        title_box.pack(side="left")

        logo = tk.Label(title_box, text="⚡", font=("Segoe UI Emoji", 20), bg="#111827", fg="#3b82f6")
        logo.pack(side="left", padx=(0, 10))

        title_lbl = tk.Label(title_box, text="AEGIS GAMING PLATFORM", font=("Segoe UI", 13, "bold"),
                             bg="#111827", fg="#ffffff")
        title_lbl.pack(anchor="w")

        sub_lbl = tk.Label(title_box, text="Warcraft III TFT 1.26a • GameRanger-Style All-In-One",
                           font=("Segoe UI", 8), bg="#111827", fg="#9ca3af")
        sub_lbl.pack(anchor="w")

        # Right status pills
        status_box = tk.Frame(header, bg="#111827")
        status_box.pack(side="right")

        self.war3_status_lbl = tk.Label(status_box, text="● 4GB LAA: Ready", font=("Segoe UI", 9, "bold"),
                                        bg="#111827", fg="#10b981", padx=8)
        self.war3_status_lbl.pack(side="left")

        btn_launch = tk.Button(status_box, text="🎮 Launch War3", font=("Segoe UI", 9, "bold"),
                               bg="#2563eb", fg="#ffffff", activebackground="#1d4ed8", activeforeground="#ffffff",
                               relief="flat", padx=12, pady=4, cursor="hand2", command=self.action_launch_war3)
        btn_launch.pack(side="left", padx=6)

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=10)

        # Tab 1: GameRanger Online Lobby
        self.tab_lobby = tk.Frame(self.notebook, bg="#0b0f19", padx=10, pady=10)
        self.notebook.add(self.tab_lobby, text=" 🌐 Online Lobby (GameRanger) ")
        self._init_lobby_tab()

        # Tab 2: Match Room & Recovery (Host LAN)
        self.tab_match = tk.Frame(self.notebook, bg="#0b0f19", padx=10, pady=10)
        self.notebook.add(self.tab_match, text=" ⚔️ Host (Offline/LAN) ")
        self._init_match_tab()

        # Tab 3: Client / Friend Mode
        self.tab_client = tk.Frame(self.notebook, bg="#0b0f19", padx=10, pady=10)
        self.notebook.add(self.tab_client, text=" 👥 Direct Client (IP Mode) ")
        self._init_client_tab()

        # Tab 4: Universal Map Converter
        self.tab_converter = tk.Frame(self.notebook, bg="#0b0f19", padx=10, pady=10)
        self.notebook.add(self.tab_converter, text=" 🛠️ Map Converter ")
        self._init_converter_tab()

        # Tab 5: Built-in WarKey & Camera
        self.tab_warkey = tk.Frame(self.notebook, bg="#0b0f19", padx=10, pady=10)
        self.notebook.add(self.tab_warkey, text=" ⌨️ WarKey & Camera ")
        self._init_warkey_tab()

        # Tab 6: Settings
        self.tab_settings = tk.Frame(self.notebook, bg="#0b0f19", padx=10, pady=10)
        self.notebook.add(self.tab_settings, text=" ⚙️ Settings ")
        self._init_settings_tab()

    def _init_lobby_tab(self):
        panes = tk.Frame(self.tab_lobby, bg="#0b0f19")
        panes.pack(fill="both", expand=True)

        # Top status bar inside tab
        top_bar = tk.Frame(panes, bg="#111827", padx=10, pady=6, relief="ridge", bd=1)
        top_bar.pack(fill="x", pady=(0, 8))

        tk.Label(top_bar, text="Тоглогчийн нэр:", font=("Segoe UI", 9, "bold"),
                 bg="#111827", fg="#e5e7eb").pack(side="left")
        self.entry_player_name = tk.Entry(top_bar, font=("Segoe UI", 9), bg="#1f2937", fg="#ffffff",
                                          insertbackground="#ffffff", relief="flat", width=14)
        self.entry_player_name.insert(0, self.lobby_svc.player_name)
        self.entry_player_name.pack(side="left", padx=6)

        btn_set_name = tk.Button(top_bar, text="Нэр Хадгалах", font=("Segoe UI", 8),
                                 bg="#374151", fg="#ffffff", relief="flat", padx=6, pady=2,
                                 cursor="hand2", command=self.action_update_name)
        btn_set_name.pack(side="left", padx=(0, 14))

        self.lbl_lobby_net_status = tk.Label(top_bar, text="● Global Broker: Холбогдож байна...",
                                             font=("Segoe UI", 9, "bold"), bg="#111827", fg="#f59e0b")
        self.lbl_lobby_net_status.pack(side="right")

        # Two columns: Left (Rooms List), Right (Active Room Panel)
        body = tk.Frame(panes, bg="#0b0f19")
        body.pack(fill="both", expand=True)

        col_rooms = tk.Frame(body, bg="#111827", padx=10, pady=10, relief="ridge", bd=1)
        col_rooms.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(col_rooms, text="НЭЭЛТТЭЙ ӨРӨӨНҮҮДИЙН ЖАГСААЛТ (LIVE ROOMS)",
                 font=("Segoe UI", 10, "bold"), bg="#111827", fg="#3b82f6").pack(anchor="w", pady=(0, 6))

        # Treeview
        tree_frame = tk.Frame(col_rooms, bg="#111827")
        tree_frame.pack(fill="both", expand=True)

        columns = ("name", "host", "map", "players", "status")
        self.tree_rooms = ttk.Treeview(tree_frame, columns=columns, show="headings", height=12)
        self.tree_rooms.heading("name", text="Өрөөний нэр")
        self.tree_rooms.heading("host", text="Хост")
        self.tree_rooms.heading("map", text="Газрын зураг")
        self.tree_rooms.heading("players", text="Тоглогч")
        self.tree_rooms.heading("status", text="Төлөв")

        self.tree_rooms.column("name", width=190)
        self.tree_rooms.column("host", width=90)
        self.tree_rooms.column("map", width=140)
        self.tree_rooms.column("players", width=60)
        self.tree_rooms.column("status", width=90)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_rooms.yview)
        self.tree_rooms.configure(yscrollcommand=scrollbar.set)
        self.tree_rooms.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree_rooms.bind("<Double-1>", lambda e: self.action_join_selected_room())

        # Room buttons below list
        btn_bar = tk.Frame(col_rooms, bg="#111827")
        btn_bar.pack(fill="x", pady=(8, 0))

        btn_join = tk.Button(btn_bar, text="🎮 Өрөөнд Нэгдэх (Join Room)", font=("Segoe UI", 9, "bold"),
                             bg="#2563eb", fg="#ffffff", activebackground="#1d4ed8",
                             relief="flat", padx=12, pady=5, cursor="hand2", command=self.action_join_selected_room)
        btn_join.pack(side="left", padx=(0, 6))

        btn_create = tk.Button(btn_bar, text="➕ Шинэ Өрөө Үүсгэх", font=("Segoe UI", 9, "bold"),
                               bg="#059669", fg="#ffffff", activebackground="#047857",
                               relief="flat", padx=12, pady=5, cursor="hand2", command=self.action_create_room_dialog)
        btn_create.pack(side="left", padx=(0, 6))

        btn_refresh = tk.Button(btn_bar, text="🔄 Шинэчлэх", font=("Segoe UI", 9),
                                bg="#374151", fg="#ffffff", relief="flat", padx=10, pady=5,
                                cursor="hand2", command=self.action_refresh_rooms)
        btn_refresh.pack(side="left")

        # Right Column: Active Room Control Center
        self.col_active_room = tk.Frame(body, bg="#111827", padx=12, pady=12, relief="ridge", bd=1, width=320)
        self.col_active_room.pack(side="right", fill="both", padx=(6, 0))
        self.col_active_room.pack_propagate(False)

        self._build_active_room_panel()

    def _build_active_room_panel(self):
        for widget in self.col_active_room.winfo_children():
            widget.destroy()

        if not self.lobby_svc.active_room:
            tk.Label(self.col_active_room, text="ӨРӨӨ СҮЛЖЭЭ (ACTIVE ROOM)",
                     font=("Segoe UI", 10, "bold"), bg="#111827", fg="#6b7280").pack(anchor="w")
            tk.Label(self.col_active_room, text="Та одоогоор өрөөнд ороогүй байна.\n\nЗүүн талын жагсаалтаас өрөө сонгоод\n'🎮 Өрөөнд Нэгдэх' товч дарах эсвэл\n'➕ Шинэ Өрөө Үүсгэх' товчийг дарна уу.",
                     font=("Segoe UI", 9), bg="#111827", fg="#9ca3af", justify="left").pack(anchor="w", pady=20)
            return

        room = self.lobby_svc.active_room
        is_host = self.lobby_svc.is_host

        tk.Label(self.col_active_room, text="СОНГОСОН ӨРӨӨ (LOBBY)", font=("Segoe UI", 10, "bold"),
                 bg="#111827", fg="#3b82f6").pack(anchor="w")

        status = room.get("status", "Waiting in Lobby")
        is_in_game = (status == "In Game")

        info_box = tk.Frame(self.col_active_room, bg="#0b0f19", padx=10, pady=8)
        info_box.pack(fill="x", pady=6)

        tk.Label(info_box, text=f"Өрөө: {room.get('room_name', 'Room')}", font=("Segoe UI", 9, "bold"),
                 bg="#0b0f19", fg="#ffffff").pack(anchor="w")
        tk.Label(info_box, text=f"Газрын зураг: {room.get('map_name', 'LoD')}", font=("Segoe UI", 8),
                 bg="#0b0f19", fg="#9ca3af").pack(anchor="w")
        tk.Label(info_box, text=f"Хост: {room.get('host_name', 'Host')}", font=("Segoe UI", 8),
                 bg="#0b0f19", fg="#10b981").pack(anchor="w")

        status_color = "#10b981" if is_in_game else "#38bdf8"
        tk.Label(info_box, text=f"Төлөв: {status}", font=("Segoe UI", 8, "bold"),
                 bg="#0b0f19", fg=status_color).pack(anchor="w")

        tk.Label(self.col_active_room, text="Тоглогчид:", font=("Segoe UI", 9, "bold"),
                 bg="#111827", fg="#e5e7eb").pack(anchor="w", pady=(8, 2))

        player_list = tk.Listbox(self.col_active_room, font=("Segoe UI", 9), bg="#0b0f19", fg="#d1d5db",
                                 relief="flat", height=5)
        for p in room.get("players", []):
            role = " [Host]" if p == room.get("host_name") else ""
            player_list.insert("end", f"● {p}{role}")
        player_list.pack(fill="x", pady=(0, 10))

        # Control Buttons - Simple & Clean (Zero Confusion)
        if is_in_game:
            # 1-CLICK ALL-IN-ONE REJOIN BUTTON FOR EVERYONE (HOST & CLIENT)
            btn_rejoin = tk.Button(self.col_active_room, text="🔄 БУЦАЖ ОРОХ (REJOIN MATCH)",
                                   font=("Segoe UI", 10, "bold"), bg="#2563eb", fg="#ffffff",
                                   activebackground="#1d4ed8", activeforeground="#ffffff",
                                   relief="flat", pady=10, cursor="hand2",
                                   command=self.action_rejoin_online_game)
            btn_rejoin.pack(fill="x", pady=(6, 4))

            lbl_hint = tk.Label(self.col_active_room,
                                text="● Тоглолт явагдаж байна.\nЭнэ ганц товчийг дарахад Save-ийг автоматаар\nтатаж аваад War3-аар шууд буцаж орно.",
                                font=("Segoe UI", 8), bg="#111827", fg="#38bdf8", justify="left")
            lbl_hint.pack(fill="x", pady=(0, 6))

            if is_host:
                btn_stop = tk.Button(self.col_active_room, text="⏹️ Тоглолтыг Дуусгах (End Match)",
                                     font=("Segoe UI", 8), bg="#374151", fg="#9ca3af",
                                     relief="flat", pady=3, cursor="hand2",
                                     command=self.action_stop_online_game)
                btn_stop.pack(fill="x", pady=(4, 0))

        elif is_host:
            # LOBBY BEFORE GAME STARTS (HOST ONLY)
            btn_start = tk.Button(self.col_active_room, text="🚀 ТОГЛООМ ЭХЛҮҮЛЭХ (START)",
                                  font=("Segoe UI", 10, "bold"), bg="#059669", fg="#ffffff",
                                  activebackground="#047857", relief="flat", pady=8, cursor="hand2",
                                  command=self.action_start_online_game)
            btn_start.pack(fill="x", pady=4)
        else:
            # LOBBY BEFORE GAME STARTS (CLIENT ONLY)
            lbl_wait = tk.Label(self.col_active_room, text="● Хост тоглоомыг эхлүүлэхийг хүлээж байна...\nЭхлэхэд War3 автоматаар нээгдэнэ.",
                                font=("Segoe UI", 8), bg="#111827", fg="#f59e0b", justify="left")
            lbl_wait.pack(fill="x", pady=6)

        btn_leave = tk.Button(self.col_active_room, text="🚪 Өрөөнөөс Гарах", font=("Segoe UI", 9),
                              bg="#4b5563", fg="#ffffff", relief="flat", pady=4, cursor="hand2",
                              command=self.action_leave_online_room)
        btn_leave.pack(fill="x", pady=(8, 0))

    def _init_client_tab(self):
        box = tk.Frame(self.tab_client, bg="#111827", padx=16, pady=16, relief="ridge", bd=1)
        box.pack(fill="both", expand=True)

        tk.Label(box, text="CLIENT / FRIEND SYNC MODE", font=("Segoe UI", 11, "bold"),
                 bg="#111827", fg="#3b82f6").pack(anchor="w")
        tk.Label(box, text="Найзууд нь энэ цонхноос хостын IP хаягийг оруулаад сүүлийн Save файлыг 0.2 секундэд\n"
                           "чимээгүй татаж авна. Ингэснээр тоглолтын дундуур хэн ч унасан гараар файл зөөхгүй шууд орно.",
                 font=("Segoe UI", 9), bg="#111827", fg="#9ca3af", justify="left").pack(anchor="w", pady=(4, 14))

        input_frame = tk.Frame(box, bg="#111827")
        input_frame.pack(fill="x", pady=6)

        tk.Label(input_frame, text="Хостын IP хаяг (Host IP / VPN IP):", font=("Segoe UI", 9, "bold"),
                 bg="#111827", fg="#e5e7eb").pack(side="left", padx=(0, 10))
        self.entry_host_ip = tk.Entry(input_frame, font=("Segoe UI", 10), bg="#1f2937", fg="#ffffff",
                                      insertbackground="#ffffff", relief="flat", width=22)
        self.entry_host_ip.insert(0, "127.0.0.1")
        self.entry_host_ip.pack(side="left", ipady=3, padx=(0, 10))

        btn_row = tk.Frame(box, bg="#111827")
        btn_row.pack(fill="x", pady=8)

        self.btn_client_connect = tk.Button(btn_row, text="📡 Холбогдох & Өрөөг LAN-д гаргах",
                                            font=("Segoe UI", 9, "bold"), bg="#2563eb", fg="#ffffff",
                                            activebackground="#1d4ed8", activeforeground="#ffffff",
                                            relief="flat", padx=12, pady=5, cursor="hand2",
                                            command=self.action_client_connect)
        self.btn_client_connect.pack(side="left", padx=(0, 6))

        self.btn_client_disconnect = tk.Button(btn_row, text="⏹️ Салгах",
                                               font=("Segoe UI", 9), bg="#4b5563", fg="#ffffff",
                                               activebackground="#374151", activeforeground="#ffffff",
                                               relief="flat", padx=10, pady=5, cursor="hand2",
                                               command=self.action_client_disconnect)
        self.btn_client_disconnect.pack(side="left", padx=(0, 6))

        btn_sync = tk.Button(btn_row, text="🔄 Save Татах", font=("Segoe UI", 9, "bold"),
                             bg="#059669", fg="#ffffff", relief="flat", padx=10, pady=5,
                             cursor="hand2", command=self.action_client_sync)
        btn_sync.pack(side="left")

        self.lbl_client_sync_result = tk.Label(box, text="Төлөв: Бэлэн (Хостын IP оруулаад 'Холбогдох' дарна уу)",
                                               font=("Segoe UI", 9), bg="#111827", fg="#9ca3af", justify="left")
        self.lbl_client_sync_result.pack(anchor="w", pady=8)

        # 1-Click Launch & Join Box
        action_card = tk.Frame(box, bg="#0b0f19", padx=14, pady=14, relief="ridge", bd=1)
        action_card.pack(fill="x", pady=10)

        tk.Label(action_card, text="🎮 Тоглоомд Нэгдэх:", font=("Segoe UI", 10, "bold"),
                 bg="#0b0f19", fg="#ffffff").pack(anchor="w")
        tk.Label(action_card, text="1. Дээрх '📡 Холбогдох & Өрөөг LAN-д гаргах' товч дарсны дараа доорх товчоор War3-аа нээнэ.\n"
                                   "2. Local Area Network руу ороход хостын өрөө шууд харагдана. Нэг товшилтоор орж тоглоно.\n"
                                   "3. Хэрэв тоглолтын дундуур хэн нэг нь fatal-даж унавал хост сэргээсний дараа 'Save Татах' дараад буцаад орно.",
                 font=("Segoe UI", 9), bg="#0b0f19", fg="#9ca3af", justify="left").pack(anchor="w", pady=(4, 10))

        btn_quick_rejoin = tk.Button(action_card, text="🔄 БУЦАЖ ОРОХ (Save Татаж аваад Шууд Орох)",
                                     font=("Segoe UI", 10, "bold"), bg="#2563eb", fg="#ffffff",
                                     activebackground="#1d4ed8", activeforeground="#ffffff",
                                     relief="flat", padx=16, pady=8, cursor="hand2",
                                     command=self.action_client_quick_rejoin)
        btn_quick_rejoin.pack(anchor="w", pady=(0, 8))

        btn_launch_friend = tk.Button(action_card, text="🚀 Зөвхөн Warcraft III-аа нээх",
                                      font=("Segoe UI", 9), bg="#374151", fg="#ffffff",
                                      relief="flat", padx=12, pady=6, cursor="hand2", command=self.action_launch_war3)
        btn_launch_friend.pack(anchor="w")

    def _init_settings_tab(self):
        box = tk.Frame(self.tab_settings, bg="#111827", padx=16, pady=16, relief="ridge", bd=1)
        box.pack(fill="both", expand=True)

        tk.Label(box, text="PLATFORM SETTINGS & HEALTH CHECK", font=("Segoe UI", 11, "bold"),
                 bg="#111827", fg="#3b82f6").pack(anchor="w")

        # Game Path
        tk.Label(box, text="Warcraft III Хавтас (Installation Path):", font=("Segoe UI", 9, "bold"),
                 bg="#111827", fg="#e5e7eb").pack(anchor="w", pady=(14, 4))
        path_box = tk.Frame(box, bg="#111827")
        path_box.pack(fill="x")
        self.entry_game_path = tk.Entry(path_box, font=("Segoe UI", 9), bg="#1f2937", fg="#ffffff",
                                        insertbackground="#ffffff", relief="flat")
        self.entry_game_path.insert(0, str(self.engine.game_dir))
        self.entry_game_path.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 8))
        btn_browse_game = tk.Button(path_box, text="📁 Сонгох...", font=("Segoe UI", 9),
                                    bg="#374151", fg="#ffffff", relief="flat", padx=10, pady=3,
                                    cursor="hand2", command=self.action_browse_game_dir)
        btn_browse_game.pack(side="left")

        # 4GB Patch Section
        patch_box = tk.Frame(box, bg="#0b0f19", padx=12, pady=12, relief="ridge", bd=1)
        patch_box.pack(fill="x", pady=14)
        tk.Label(patch_box, text="4GB Large Address Aware Patch (RAM санах ой нэмэгдүүлэгч):",
                 font=("Segoe UI", 9, "bold"), bg="#0b0f19", fg="#ffffff").pack(anchor="w")
        tk.Label(patch_box, text="LoD тоглолтын дундуур RAM дуусч Fatal Error гарахаас 90% сэргийлдэг албан ёсны патч.",
                 font=("Segoe UI", 8), bg="#0b0f19", fg="#9ca3af").pack(anchor="w", pady=2)
        btn_apply_4gb = tk.Button(patch_box, text="⚡ 4GB Патч Шалгах & Суулгах", font=("Segoe UI", 9, "bold"),
                                  bg="#059669", fg="#ffffff", relief="flat", padx=12, pady=5,
                                  cursor="hand2", command=self.action_apply_4gb)
        btn_apply_4gb.pack(anchor="w", pady=(6, 0))

    def _init_match_tab(self):
        panes = tk.Frame(self.tab_match, bg="#0b0f19")
        panes.pack(fill="both", expand=True)

        # Left Column: Host Controls
        col_host = tk.Frame(panes, bg="#111827", padx=14, pady=14, relief="ridge", bd=1)
        col_host.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(col_host, text="HOST MATCH CONTROLS", font=("Segoe UI", 10, "bold"),
                 bg="#111827", fg="#3b82f6").pack(anchor="w")

        tk.Label(col_host, text="Өрөөний Нэр (Room Name):", font=("Segoe UI", 9),
                 bg="#111827", fg="#9ca3af").pack(anchor="w", pady=(10, 2))
        self.entry_room_name = tk.Entry(col_host, font=("Segoe UI", 10), bg="#1f2937", fg="#ffffff",
                                        insertbackground="#ffffff", relief="flat")
        self.entry_room_name.insert(0, "[Aegis] DotA LoD 5v5 Room")
        self.entry_room_name.pack(fill="x", ipady=4)

        tk.Label(col_host, text="Газрын Зураг (Map):", font=("Segoe UI", 9),
                 bg="#111827", fg="#9ca3af").pack(anchor="w", pady=(10, 2))
        
        # Discover maps in Maps\Download
        maps = []
        if MAPS_DIR.is_dir():
            for f in MAPS_DIR.glob("*.w3x"):
                if "probe" in f.name.lower() or "[aegis-ready]" in f.name.lower():
                    continue
                maps.append(f.name)
        if "DotA LoD 6.85m Aegis.w3x" in maps:
            maps.remove("DotA LoD 6.85m Aegis.w3x")
            maps.insert(0, "DotA LoD 6.85m Aegis.w3x")
        elif not maps:
            maps = ["DotA LoD 6.85m Aegis.w3x"]
        
        self.combo_map = ttk.Combobox(col_host, values=maps, state="readonly", font=("Segoe UI", 9))
        self.combo_map.set(maps[0])
        self.combo_map.pack(fill="x", ipady=2)

        # Host Action Buttons
        btn_box = tk.Frame(col_host, bg="#111827")
        btn_box.pack(fill="x", pady=14)

        self.btn_host_normal = tk.Button(btn_box, text="⚡ Шинэ Тоглолт Үүсгэх (Host Game)",
                                         font=("Segoe UI", 10, "bold"), bg="#059669", fg="#ffffff",
                                         activebackground="#047857", activeforeground="#ffffff",
                                         relief="flat", pady=6, cursor="hand2", command=self.action_host_normal)
        self.btn_host_normal.pack(fill="x", pady=3)

        self.btn_stop_host = tk.Button(btn_box, text="⏹️ Өрөөг Хаах (Stop Host)",
                                       font=("Segoe UI", 9), bg="#4b5563", fg="#ffffff",
                                       activebackground="#374151", activeforeground="#ffffff",
                                       relief="flat", pady=4, cursor="hand2", command=self.action_stop_host)
        self.btn_stop_host.pack(fill="x", pady=3)

        # 1-CLICK INSTANT CRASH RECOVERY BOX
        rec_box = tk.Frame(col_host, bg="#1c1917", padx=12, pady=12, relief="groove", bd=1)
        rec_box.pack(fill="x", pady=(10, 0))

        tk.Label(rec_box, text="🛡️ 1-CLICK CRASH RECOVERY", font=("Segoe UI", 10, "bold"),
                 bg="#1c1917", fg="#f59e0b").pack(anchor="w")
        tk.Label(rec_box, text="Хэн нэгэн fatal-даж унасан бол доорх товчийг дарахад\nхамгийн сүүлийн хадгалалтаар өрөөг хормын төдийд сэргээнэ.",
                 font=("Segoe UI", 8), bg="#1c1917", fg="#d6d3d1", justify="left").pack(anchor="w", pady=(2, 8))

        self.btn_restore = tk.Button(rec_box, text="🔄 1-CLICK СЭРГЭЭХ (Restore Last Crash)",
                                     font=("Segoe UI", 10, "bold"), bg="#d97706", fg="#ffffff",
                                     activebackground="#b45309", activeforeground="#ffffff",
                                     relief="flat", pady=6, cursor="hand2", command=self.action_restore_match)
        self.btn_restore.pack(fill="x")

        # LOBBY COMMANDS CHEAT SHEET
        cmd_box = tk.Frame(col_host, bg="#0f172a", padx=10, pady=8, relief="groove", bd=1)
        cmd_box.pack(fill="x", pady=(10, 0))

        tk.Label(cmd_box, text="📌 Өрөөний Командууд (Lobby Chat):", font=("Segoe UI", 9, "bold"),
                 bg="#0f172a", fg="#38bdf8").pack(anchor="w")
        commands_text = (
            "• !fakeplayer  -> 1 хүнтэй тест хийхэд bot нэмэх\n"
            "• !start force -> Тоглоомыг хүчээр эхлүүлэх\n"
            "• !swap 1 6    -> 1-р тоглогчийг 2-р баг руу шилжүүлэх\n"
            "• !sp          -> Бүх тоглогчдыг хоёр багт санамсаргүй хуваарилах\n"
            "• !kick <нэр>  -> Тоглогчийг өрөөнөөс гаргах"
        )
        tk.Label(cmd_box, text=commands_text, font=("Consolas", 8),
                 bg="#0f172a", fg="#cbd5e1", justify="left").pack(anchor="w", pady=(3, 0))

        # Right Column: Live Status & Log
        col_status = tk.Frame(panes, bg="#111827", padx=14, pady=14, relief="ridge", bd=1)
        col_status.pack(side="right", fill="both", expand=True, padx=(6, 0))

        tk.Label(col_status, text="SYSTEM STATUS & LOG", font=("Segoe UI", 10, "bold"),
                 bg="#111827", fg="#3b82f6").pack(anchor="w")

        info_frame = tk.Frame(col_status, bg="#0b0f19", padx=10, pady=8)
        info_frame.pack(fill="x", pady=(8, 10))

        self.lbl_engine_status = tk.Label(info_frame, text="Engine: Одоогоор унтарсан байна",
                                          font=("Segoe UI", 9), bg="#0b0f19", fg="#9ca3af")
        self.lbl_engine_status.pack(anchor="w")

        self.lbl_active_save = tk.Label(info_frame, text="Сүүлийн Save: Шалгаж байна...",
                                        font=("Segoe UI", 9), bg="#0b0f19", fg="#9ca3af")
        self.lbl_active_save.pack(anchor="w")

        self.lbl_sync_status = tk.Label(info_frame, text="Silent Sync Server: Порт 6205",
                                        font=("Segoe UI", 9), bg="#0b0f19", fg="#10b981")
        self.lbl_sync_status.pack(anchor="w")

        # Event Log
        tk.Label(col_status, text="Үйлдлийн бүртгэл:", font=("Segoe UI", 8, "bold"),
                 bg="#111827", fg="#6b7280").pack(anchor="w")
        self.txt_log = tk.Text(col_status, font=("Consolas", 9), bg="#0b0f19", fg="#d1d5db",
                               relief="flat", height=12)
        self.txt_log.pack(fill="both", expand=True, pady=4)
        self.log("Aegis Platform ready.")

    def _init_converter_tab(self):
        box = tk.Frame(self.tab_converter, bg="#111827", padx=16, pady=16, relief="ridge", bd=1)
        box.pack(fill="both", expand=True)

        tk.Label(box, text="UNIVERSAL DOTA LOD MAP CONVERTER (MAP FORGE)",
                 font=("Segoe UI", 11, "bold"), bg="#111827", fg="#3b82f6").pack(anchor="w")
        tk.Label(box, text="Хүмүүс зөвхөн 6.85m биш, өөр олон төрлийн LoD (6.74c, 6.81, 6.86 гэх мэт) тоглодог.\n"
                           "Энэхүү хэрэгсэл нь дурын LoD map-ийг Crash-Recovery болон -cam зайн удирдлагатай болгон 1 секундэд хөрвүүлнэ.",
                 font=("Segoe UI", 9), bg="#111827", fg="#9ca3af", justify="left").pack(anchor="w", pady=(4, 14))

        file_pick = tk.Frame(box, bg="#111827")
        file_pick.pack(fill="x", pady=6)

        self.entry_conv_map = tk.Entry(file_pick, font=("Segoe UI", 9), bg="#1f2937", fg="#ffffff",
                                       insertbackground="#ffffff", relief="flat")
        default_lod = MAPS_DIR / "DotA LoD 6.85m.w3x"
        if default_lod.is_file():
            self.entry_conv_map.insert(0, str(default_lod))
        self.entry_conv_map.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 8))

        btn_browse = tk.Button(file_pick, text="📁 Map сонгох...", font=("Segoe UI", 9),
                               bg="#374151", fg="#ffffff", relief="flat", padx=10, pady=3,
                               cursor="hand2", command=self.action_browse_map)
        btn_browse.pack(side="left")

        # Options
        self.var_cam = tk.BooleanVar(value=True)
        chk_cam = tk.Checkbutton(box, text="'-cam 1.6' болон '-cam 2' камер холдуулах коммандыг автоматаар залгах (6.74c гэх мэт map-д)",
                                 variable=self.var_cam, font=("Segoe UI", 9), bg="#111827", fg="#e5e7eb",
                                 selectcolor="#1f2937", activebackground="#111827", activeforeground="#ffffff")
        chk_cam.pack(anchor="w", pady=6)

        btn_convert = tk.Button(box, text="⚡ Газрын Зургийг Хөрвүүлэх (Convert Map Now)",
                                font=("Segoe UI", 10, "bold"), bg="#2563eb", fg="#ffffff",
                                activebackground="#1d4ed8", activeforeground="#ffffff",
                                relief="flat", padx=16, pady=8, cursor="hand2", command=self.action_convert_map)
        btn_convert.pack(anchor="w", pady=10)

        self.lbl_conv_result = tk.Label(box, text="", font=("Segoe UI", 9, "bold"), bg="#111827", fg="#10b981")
        self.lbl_conv_result.pack(anchor="w", pady=4)

    def _init_warkey_tab(self):
        box = tk.Frame(self.tab_warkey, bg="#111827", padx=16, pady=16, relief="ridge", bd=1)
        box.pack(fill="both", expand=True)

        tk.Label(box, text="BUILT-IN WARKEY & CAMERA CONTROLS",
                 font=("Segoe UI", 11, "bold"), bg="#111827", fg="#3b82f6").pack(anchor="w")
        tk.Label(box, text="Нэмэлт WarKey.exe татаж суулгах шаардлагагүй. Тоглоом доторх 6 inventory slot-ийг хүссэн товчлуур дээрээ тохируулна.\n"
                           "Чат нээхэд (Enter дарахад) автомат түр зогсож, энгийн бичилтэд саад болохгүй.",
                 font=("Segoe UI", 9), bg="#111827", fg="#9ca3af", justify="left").pack(anchor="w", pady=(4, 14))

        # WarKey Toggle
        self.var_warkey_enabled = tk.BooleanVar(value=False)
        chk_warkey = tk.Checkbutton(box, text="⚡ WarKey Inventory Remapper Идэвхжүүлэх (Active in Warcraft III)",
                                    variable=self.var_warkey_enabled, font=("Segoe UI", 10, "bold"),
                                    bg="#111827", fg="#10b981", selectcolor="#1f2937",
                                    activebackground="#111827", activeforeground="#10b981",
                                    command=self.action_toggle_warkey)
        chk_warkey.pack(anchor="w", pady=4)

        # Inventory Grid (2x3)
        grid_frame = tk.Frame(box, bg="#0b0f19", padx=14, pady=14, relief="ridge", bd=1)
        grid_frame.pack(anchor="w", pady=10)

        tk.Label(grid_frame, text="Slot 1 (NumPad 7):  Space (Хуваарь 1)", font=("Segoe UI", 9, "bold"),
                 bg="#0b0f19", fg="#ffffff").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        tk.Label(grid_frame, text="Slot 2 (NumPad 8):  1", font=("Segoe UI", 9, "bold"),
                 bg="#0b0f19", fg="#ffffff").grid(row=0, column=1, padx=10, pady=6, sticky="w")
        tk.Label(grid_frame, text="Slot 3 (NumPad 4):  2", font=("Segoe UI", 9, "bold"),
                 bg="#0b0f19", fg="#ffffff").grid(row=1, column=0, padx=10, pady=6, sticky="w")
        tk.Label(grid_frame, text="Slot 4 (NumPad 5):  3", font=("Segoe UI", 9, "bold"),
                 bg="#0b0f19", fg="#ffffff").grid(row=1, column=1, padx=10, pady=6, sticky="w")
        tk.Label(grid_frame, text="Slot 5 (NumPad 1):  4", font=("Segoe UI", 9, "bold"),
                 bg="#0b0f19", fg="#ffffff").grid(row=2, column=0, padx=10, pady=6, sticky="w")
        tk.Label(grid_frame, text="Slot 6 (NumPad 2):  5", font=("Segoe UI", 9, "bold"),
                 bg="#0b0f19", fg="#ffffff").grid(row=2, column=1, padx=10, pady=6, sticky="w")

        # Camera Quick Reference
        cam_ref = tk.Frame(box, bg="#111827")
        cam_ref.pack(fill="x", pady=10)
        tk.Label(cam_ref, text="Камер холдуулах түргэн командын заавар:", font=("Segoe UI", 9, "bold"),
                 bg="#111827", fg="#f59e0b").pack(anchor="w")
        tk.Label(cam_ref, text="• Тоглоом дотор чатанд '-cam 1.6' эсвэл '-cam 2' гэж бичихэд дэлгэц хормын зуур холдоно.\n"
                               "• Буцааж хэвийн болгох бол '-cam 1' гэж бичнэ.",
                 font=("Segoe UI", 9), bg="#111827", fg="#d1d5db", justify="left").pack(anchor="w", pady=2)

    def _build_footer(self):
        footer = tk.Frame(self, bg="#0b0f19", padx=14, pady=6)
        footer.pack(fill="x", side="bottom")
        tk.Label(footer, text="Aegis Reconnect Platform • Ready for Global Release",
                 font=("Segoe UI", 8), bg="#0b0f19", fg="#6b7280").pack(side="left")
        self.lbl_clock = tk.Label(footer, text="", font=("Segoe UI", 8), bg="#0b0f19", fg="#6b7280")
        self.lbl_clock.pack(side="right")
        self._update_clock()

    def _update_clock(self):
        self.lbl_clock.config(text=time.strftime("%Y-%m-%d %H:%M:%S"))
        # Refresh latest save info
        latest = get_latest_save(SAVE_DIR)
        if latest:
            self.lbl_active_save.config(text=f"Сүүлийн Save: {latest.name[:25]}... ({latest.stat().st_size} bytes)")
        self.after(2000, self._update_clock)

    def log(self, text: str):
        self.txt_log.insert("end", f"[{time.strftime('%H:%M:%S')}] {text}\n")
        self.txt_log.see("end")

    # Actions
    def action_launch_war3(self):
        try:
            player_name = "ZEV"
            if hasattr(self, "entry_player_name"):
                player_name = self.entry_player_name.get().strip() or "ZEV"
            elif hasattr(self, "lobby_svc") and self.lobby_svc.player_name:
                player_name = self.lobby_svc.player_name
            self.engine.launch_war3(player_name=player_name)
            self.log(f"Warcraft III process started (Player: {player_name}).")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def action_host_normal(self):
        room_name = self.entry_room_name.get().strip() or "[Aegis] LoD Match"
        map_name = self.combo_map.get().strip()
        map_file = MAPS_DIR / map_name
        owner_name = self.entry_player_name.get().strip() or "ZEV"
        self.log(f"Starting host for room: {room_name} with map: {map_name} (Owner: {owner_name})...")
        try:
            threading.Thread(target=self._run_host_thread, args=(map_file, room_name, owner_name), daemon=True).start()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _run_host_thread(self, map_file: Path, room_name: str, owner_name: str = "ZEV"):
        try:
            self.engine.host_normal_room(map_file, room_name, owner_name=owner_name)
            self.lbl_engine_status.config(text=f"Engine: Ажиллаж байна ({room_name})", fg="#10b981")
            self.log(f"SUCCESS: Room '{room_name}' is now broadcasting in LAN!")
            self.log("Launching Warcraft III with GameRanger-style auto-join...")
            self.action_launch_war3()
        except Exception as e:
            self.lbl_engine_status.config(text="Engine: Алдаа гарлаа", fg="#ef4444")
            self.log(f"Host error: {e}")
            messagebox.showerror("Host Error", str(e))

    def action_restore_match(self):
        self.log("Initiating 1-Click Crash Recovery...")
        owner_name = self.entry_player_name.get().strip() or "ZEV"
        try:
            threading.Thread(target=self._run_restore_thread, args=(owner_name,), daemon=True).start()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _run_restore_thread(self, owner_name: str = "ZEV"):
        try:
            self.engine.host_recovered_match(owner_name=owner_name)
            self.lbl_engine_status.config(text=f"Engine: RESTORED ROOM ACTIVE", fg="#f59e0b")
            self.log("SUCCESS: 1-Click Recovery room is ready! Launching War3 with auto-join...")
            self.action_launch_war3()
            messagebox.showinfo("Recovery Ready", "Сэргээсэн өрөө LAN дээр бэлэн боллоо!\nТоглолт зогссон секундээсээ шууд үргэлжилнэ.")
        except Exception as e:
            self.log(f"Recovery error: {e}")
            messagebox.showerror("Recovery Error", str(e))

    def action_stop_host(self):
        self.engine.stop()
        self.lbl_engine_status.config(text="Engine: Зогссон", fg="#9ca3af")
        self.log("Host engine stopped.")

    def action_browse_map(self):
        filename = filedialog.askopenfilename(
            title="LoD Map (.w3x) сонгох",
            initialdir=str(MAPS_DIR),
            filetypes=[("Warcraft III Map", "*.w3x")]
        )
        if filename:
            self.entry_conv_map.delete(0, "end")
            self.entry_conv_map.insert(0, filename)

    def action_convert_map(self):
        p = Path(self.entry_conv_map.get().strip())
        if not p.is_file():
            messagebox.showerror("Error", "Сонгосон файл олдсонгүй!")
            return
        enable_cam = self.var_cam.get()
        self.lbl_conv_result.config(text="Хөрвүүлж байна...", fg="#f59e0b")
        self.log(f"Converting map: {p.name} (Camera Zoom: {enable_cam})...")
        try:
            out = convert_map(p, enable_cam=enable_cam)
            self.lbl_conv_result.config(text=f"АМЖИЛТТАЙ! Шинэ map: {out.name}", fg="#10b981")
            self.log(f"Converted map created: {out}")
            messagebox.showinfo("Conversion Complete", f"Газрын зураг амжилттай хөрвүүлэгдлээ:\n{out.name}\n\nЭнэ map нь одоо Save/Load Reconnect болон -cam зайн удирдлагатай боллоо!")
        except Exception as e:
            self.lbl_conv_result.config(text=f"Алдаа: {e}", fg="#ef4444")
            self.log(f"Conversion error: {e}")

    def action_toggle_warkey(self):
        if self.var_warkey_enabled.get():
            self.warkey.start()
            self.log("WarKey ENABLED: Space, 1, 2, 3, 4, 5 remapped to NumPad inventory slots.")
        else:
            self.warkey.stop()
            self.log("WarKey DISABLED.")

    def action_client_connect(self):
        host_ip = self.entry_host_ip.get().strip() or "127.0.0.1"
        self.lbl_client_sync_result.config(text=f"Холбогдож байна ({host_ip})...", fg="#f59e0b")
        self.log(f"Connecting to host at {host_ip}...")

        def _do_connect():
            try:
                status = get_host_status(host_ip)
                if not status:
                    self.lbl_client_sync_result.config(
                        text=f"Алдаа: Хост {host_ip} руу холбогдож чадсангүй (IP хаяг эсвэл VPN-ээ шалгана уу).",
                        fg="#ef4444"
                    )
                    self.log(f"Connection failed to host {host_ip}")
                    return

                room_name = status.get("room_name") or "[Aegis Room]"
                room_adv_b64 = status.get("room_adv")
                adv_bytes = base64.b64decode(room_adv_b64) if room_adv_b64 else None

                # Start local client proxy tunnel
                if self.client_tunnel:
                    self.client_tunnel.stop()
                self.client_tunnel = ClientTunnel(host_ip=host_ip)
                self.client_tunnel.start_proxy()
                if adv_bytes:
                    self.client_tunnel.start_local_broadcast(adv_bytes)

                # Sync save if available
                save_msg = ""
                if status.get("latest_name"):
                    save_res = sync_save_from_host(host_ip)
                    if save_res:
                        save_msg = f" (Сүүлийн Save: {save_res.name})"

                self.lbl_client_sync_result.config(
                    text=f"● АМЖИЛТТАЙ ХОЛБОГДЛОО: '{room_name}'{save_msg}\nОдоо 'Warcraft III-аа нээж LAN руу орох' дарж шууд нэгдэнэ үү!",
                    fg="#10b981"
                )
                self.log(f"SUCCESS: Connected to room '{room_name}'. Tunnel active, reflected to LAN.")
            except Exception as e:
                self.lbl_client_sync_result.config(text=f"Алдаа: {e}", fg="#ef4444")
                self.log(f"Client tunnel error: {e}")

        threading.Thread(target=_do_connect, daemon=True).start()

    def action_client_disconnect(self):
        if self.client_tunnel:
            self.client_tunnel.stop()
            self.client_tunnel = None
        self.lbl_client_sync_result.config(text="Төлөв: Холболт салгагдлаа.", fg="#9ca3af")
        self.log("Client tunnel disconnected.")

    def action_client_sync(self):
        host_ip = self.entry_host_ip.get().strip() or "127.0.0.1"
        self.lbl_client_sync_result.config(text=f"Татаж байна ({host_ip}:6205)...", fg="#f59e0b")
        self.log(f"Contacting host at {host_ip}:6205 for latest save...")

        def _do_sync():
            res = sync_save_from_host(host_ip)
            if res:
                self.lbl_client_sync_result.config(
                    text=f"АМЖИЛТТАЙ: '{res.name}' файлыг чимээгүй татлаа! LAN руу орж болно.",
                    fg="#10b981"
                )
                self.log(f"SUCCESS: Synced '{res.name}' ({res.stat().st_size} bytes) from host.")
            else:
                self.lbl_client_sync_result.config(
                    text="Алдаа: Хостоос save файл татаж чадсангүй (IP эсвэл Port шалгана уу).",
                    fg="#ef4444"
                )
                self.log("Failed to sync save from host.")

        threading.Thread(target=_do_sync, daemon=True).start()

    def action_client_quick_rejoin(self):
        host_ip = self.entry_host_ip.get().strip() or "127.0.0.1"
        self.log(f"[1-Click Rejoin] Шууд буцаж орох эхэлж байна (Host: {host_ip})...")

        def _do_quick():
            try:
                # 1. Start tunnel
                if self.client_tunnel:
                    self.client_tunnel.stop()
                self.client_tunnel = ClientTunnel(host_ip=host_ip)
                self.client_tunnel.start_proxy()

                # 2. Sync save
                status_data = None
                try:
                    status_data = get_host_status(host_ip)
                    sync_save_from_host(host_ip)
                except Exception:
                    pass

                # 3. Broadcast room in LAN
                if status_data and status_data.get("room_adv"):
                    adv_bytes = base64.b64decode(status_data["room_adv"])
                    self.client_tunnel.start_local_broadcast(adv_bytes)

                # 4. Launch War3 and auto-join
                self.log("[1-Click Rejoin] Warcraft III нээгдэж байна...")
                self.action_launch_war3()
            except Exception as e:
                self.log(f"[1-Click Rejoin Error]: {e}")
                messagebox.showerror("Rejoin Error", str(e))

        threading.Thread(target=_do_quick, daemon=True).start()

    def action_browse_game_dir(self):
        d = filedialog.askdirectory(title="Warcraft III хавтас сонгох", initialdir=str(self.engine.game_dir))
        if d:
            p = Path(d)
            if (p / "war3.exe").is_file():
                self.entry_game_path.delete(0, "end")
                self.entry_game_path.insert(0, str(p))
                self.engine.game_dir = p
                self.log(f"Warcraft III directory set to: {p}")
            else:
                messagebox.showerror("Error", "Сонгосон хавтас дотор war3.exe олдсонгүй!")

    def action_apply_4gb(self):
        p = Path(self.entry_game_path.get().strip())
        patched = apply_4gb_patch(p)
        if patched:
            messagebox.showinfo("4GB Patch", "war3.exe дээр 4GB Patch амжилттай суулаа!\nОдоо тоглолт дундуур RAM дуусч унахгүй.")
            self.log("4GB Patch applied to war3.exe.")
        else:
            messagebox.showinfo("4GB Patch", "war3.exe дээр 4GB Patch хэдийнэ идэвхтэй байна (OK).")
            self.log("4GB Patch verified (already active).")

    def _start_lobby_service(self):
        ok = self.lobby_svc.start(on_rooms_updated=self._on_rooms_updated)
        if ok:
            self.lbl_lobby_net_status.config(text="● Global Lobby: Холбогдсон", fg="#10b981")
            self.log("Connected to global GameRanger-style signaling lobby.")
        else:
            self.lbl_lobby_net_status.config(text="● Global Lobby: Офлайн", fg="#ef4444")
            self.log("Warning: Could not connect to global lobby broker.")

    def _on_rooms_updated(self, rooms: list[dict]):
        self.after(0, self._render_rooms_tree, rooms)

    def _render_rooms_tree(self, rooms: list[dict]):
        selected = self.tree_rooms.selection()
        sel_id = selected[0] if selected else None

        for item in self.tree_rooms.get_children():
            self.tree_rooms.delete(item)

        for r in rooms:
            rid = r.get("room_id")
            name = r.get("room_name", "Room")
            host = r.get("host_name", "Host")
            map_name = r.get("map_name", "LoD")
            count = len(r.get("players", []))
            max_p = r.get("max_players", 10)
            status = r.get("status", "Waiting")
            item = self.tree_rooms.insert("", "end", iid=rid, values=(name, host, map_name, f"{count}/{max_p}", status))
            if sel_id == rid:
                self.tree_rooms.selection_set(item)

    def _on_room_state_changed(self, room: dict | None):
        self.after(0, self._build_active_room_panel)

    def _on_client_game_start(self, data: dict):
        room_name = self.lobby_svc.active_room.get("room_name") if self.lobby_svc.active_room else "Game"
        self.log(f"[Lobby] Host started game: {room_name}! Preparing War3...")
        room_adv_b64 = data.get("room_adv")
        adv_bytes = base64.b64decode(room_adv_b64) if room_adv_b64 else None
        host_ip = data.get("host_ip", "127.0.0.1")

        # Start client proxy tunnel
        if self.client_tunnel:
            self.client_tunnel.stop()
        self.client_tunnel = ClientTunnel(host_ip=host_ip)
        self.client_tunnel.start_proxy()
        if adv_bytes:
            self.client_tunnel.start_local_broadcast(adv_bytes)

        # Launch War3
        self.action_launch_war3()
        self.log(f"[Lobby] Host started match '{room_name}'! Warcraft III launched with auto-join.")

    def _on_client_recovery(self, data: dict):
        self.log("[Lobby] Host triggered 1-Click Crash Recovery! Syncing state...")
        host_ip = data.get("host_ip", "127.0.0.1")
        sync_save_from_host(host_ip)
        room_adv_b64 = data.get("room_adv")
        adv_bytes = base64.b64decode(room_adv_b64) if room_adv_b64 else None

        if self.client_tunnel and adv_bytes:
            self.client_tunnel.start_local_broadcast(adv_bytes)

        self.action_launch_war3()
        self.log("[Lobby] Host recovered match! Warcraft III launched with auto-join.")

    def action_update_name(self):
        new_name = self.entry_player_name.get().strip()
        if new_name:
            self.lobby_svc.player_name = new_name
            self.log(f"Player nickname updated to: {new_name}")
            messagebox.showinfo("Nickname", f"Таны нэр амжилттай хадгалагдлаа: {new_name}")

    def action_refresh_rooms(self):
        self.log("Refreshing room list from global broker...")
        self.lobby_svc.sig.publish(f"{TOPIC_ROOMS}/query", {"action": "list_request"})

    def action_create_room_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Шинэ Өрөө Үүсгэх")
        dialog.geometry("380x280")
        dialog.configure(bg="#111827")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="ШИНЭ ӨРӨӨ ҮҮСГЭХ", font=("Segoe UI", 11, "bold"),
                 bg="#111827", fg="#3b82f6").pack(anchor="w", padx=16, pady=(14, 8))

        tk.Label(dialog, text="Өрөөний нэр:", font=("Segoe UI", 9),
                 bg="#111827", fg="#9ca3af").pack(anchor="w", padx=16)
        entry_rname = tk.Entry(dialog, font=("Segoe UI", 10), bg="#1f2937", fg="#ffffff", relief="flat")
        entry_rname.insert(0, f"[Aegis] DotA LoD {self.lobby_svc.player_name}")
        entry_rname.pack(fill="x", padx=16, pady=(2, 10))

        tk.Label(dialog, text="Газрын зураг (Map):", font=("Segoe UI", 9),
                 bg="#111827", fg="#9ca3af").pack(anchor="w", padx=16)
        maps = []
        if MAPS_DIR.is_dir():
            for f in MAPS_DIR.glob("*.w3x"):
                if "probe" in f.name.lower() or "[aegis-ready]" in f.name.lower():
                    continue
                maps.append(f.name)
        if "DotA LoD 6.85m Aegis.w3x" in maps:
            maps.remove("DotA LoD 6.85m Aegis.w3x")
            maps.insert(0, "DotA LoD 6.85m Aegis.w3x")
        elif not maps:
            maps = ["DotA LoD 6.85m Aegis.w3x"]
        combo_m = ttk.Combobox(dialog, values=maps, state="readonly", font=("Segoe UI", 9))
        combo_m.set(maps[0])
        combo_m.pack(fill="x", padx=16, pady=(2, 16))

        def _do_create():
            rname = entry_rname.get().strip() or "LoD Match"
            mname = combo_m.get().strip()
            dialog.destroy()
            self.lobby_svc.create_online_room(rname, mname)
            self.log(f"Created online room: '{rname}' (Map: {mname}). Waiting for friends...")

        btn_confirm = tk.Button(dialog, text="✅ Өрөө Үүсгэх", font=("Segoe UI", 10, "bold"),
                                bg="#059669", fg="#ffffff", relief="flat", pady=6, cursor="hand2", command=_do_create)
        btn_confirm.pack(fill="x", padx=16, pady=8)

    def action_join_selected_room(self):
        sel = self.tree_rooms.selection()
        if not sel:
            messagebox.showwarning("Warning", "Нэгдэх өрөөгөө жагсаалтаас сонгоно уу.")
            return
        room_id = sel[0]
        ok = self.lobby_svc.join_online_room(room_id)
        if ok:
            rname = self.lobby_svc.active_room.get("room_name")
            self.log(f"Joined online room: '{rname}'. Waiting for host to start...")
        else:
            messagebox.showerror("Error", "Сонгосон өрөөнд нэгдэж чадсангүй.")

    def action_start_online_game(self):
        if not self.lobby_svc.active_room or not self.lobby_svc.is_host:
            return
        rname = self.lobby_svc.active_room.get("room_name", "LoD Match")
        mname = self.lobby_svc.active_room.get("map_name", "DotA LoD 6.85m Aegis.w3x")
        map_file = MAPS_DIR / mname
        self.log(f"Host launching match: '{rname}'...")

        def _do_start():
            try:
                self.engine.host_normal_room(map_file, rname, owner_name=self.lobby_svc.player_name)
                room_adv = self.engine.captured_adv
                self.lobby_svc.broadcast_game_start(room_adv)
                self.log(f"SUCCESS: Match '{rname}' started! Launching War3 with auto-join...")
                self.action_launch_war3()
            except Exception as e:
                self.log(f"Error launching match: {e}")
                messagebox.showerror("Error", str(e))

        threading.Thread(target=_do_start, daemon=True).start()

    def action_rejoin_online_game(self):
        if not self.lobby_svc.active_room:
            return
        room = self.lobby_svc.active_room
        is_host = self.lobby_svc.is_host
        rname = room.get("room_name", "LoD Match")
        self.log(f"[Rejoin] 'Буцаж орох' эхэлж байна: '{rname}'...")

        def _do_rejoin():
            try:
                if is_host:
                    # HOST REJOIN LOGIC
                    # Test if the match server on port 6200 is ACTUALLY LISTENING
                    port_alive = False
                    try:
                        with socket.create_connection(("127.0.0.1", 6200), timeout=0.6):
                            port_alive = True
                    except Exception:
                        port_alive = False

                    if port_alive:
                        self.log("[Host Rejoin] Шууд тоглолт сервер дээр хүлээж байна. War3-аар холбогдож байна...")
                    else:
                        # Port 6200 is dead! The match ended or dropped. Stop any old ghost broadcasts!
                        self.log("[Host Rejoin] Өрөө хаагдсан байна. Өрөөг шинэчлэн бэлдэж байна...")
                        self.engine.stop_broadcast()

                        latest_save = get_latest_save(SAVE_DIR)
                        if latest_save and latest_save.is_file() and latest_save.stat().st_size > 1000:
                            self.log(f"[Host Rejoin] Сүүлийн Save-ээр сэргээж үүсгэж байна: {latest_save.name}...")
                            self.engine.host_recovered_match(
                                save_file=latest_save,
                                room_name=f"[Restore] {rname[:15]}",
                                owner_name=self.lobby_svc.player_name
                            )
                            room_adv = self.engine.captured_adv
                            self.lobby_svc.broadcast_recovery_start(room_adv, latest_save.name)
                        else:
                            # Re-host clean room with the same map & name
                            self.log(f"[Host Rejoin] Шинэ өрөө дахин үүсгэж байна: {rname}...")
                            mname = room.get("map_name", "DotA LoD 6.85m Aegis.w3x")
                            map_file = MAPS_DIR / mname
                            self.engine.host_normal_room(map_file, rname, owner_name=self.lobby_svc.player_name)
                            room_adv = self.engine.captured_adv
                            self.lobby_svc.broadcast_game_start(room_adv)

                        self.log("[Host Rejoin] Өрөө амжилттай бэлэн боллоо!")

                    # Launch War3 with native DirectX 1024x768 & auto-navigator
                    self.action_launch_war3()
                    self.log("[Host Rejoin] Warcraft III нээгдлээ. Local Area Network руу орж байна...")
                else:
                    # CLIENT REJOIN LOGIC
                    host_ip = room.get("ip") or room.get("host_ip") or "127.0.0.1"
                    self.log(f"[Client Rejoin] Хосттой холбогдож байна ({host_ip}:6205)...")

                    status_data = get_host_status(host_ip)
                    if not status_data:
                        self.log("[Client Rejoin] Анхааруулга: Хост өрөөгөө хараахан сэргээгээгүй байна.")
                        messagebox.showwarning(
                            "Хүлээх",
                            "Хост тоглолтоо хараахан сэргээж нээгээгүй байна.\n\nХост эхлээд өөрийн компьютероос 'Буцаж орох' товчийг дарсны дараа та орно уу."
                        )
                        return

                    # 1. Silently pull latest save from host
                    try:
                        saved_path = sync_save_from_host(host_ip)
                        if saved_path:
                            self.log(f"[Client Rejoin] Сүүлийн Save татагдлаа: {saved_path.name}")
                    except Exception as se:
                        self.log(f"[Client Rejoin] Save татах мэдэгдэл: {se}")

                    # 2. Setup ClientTunnel and Local Broadcast
                    if self.client_tunnel:
                        self.client_tunnel.stop()
                    self.client_tunnel = ClientTunnel(host_ip=host_ip)
                    self.client_tunnel.start_proxy()

                    adv_b64 = room.get("room_adv") or status_data.get("room_adv")
                    if adv_b64:
                        adv_bytes = base64.b64decode(adv_b64)
                        self.client_tunnel.start_local_broadcast(adv_bytes)

                    # 3. Launch War3 with native DirectX 1024x768 & auto-navigator
                    self.action_launch_war3()
                    self.log("[Client Rejoin] Warcraft III нээгдлээ. Тоглоом руу орж байна...")
            except Exception as e:
                self.log(f"[Rejoin Алдаа]: {e}")
                messagebox.showerror("Алдаа", f"Тоглоом руу буцаж ороход алдаа гарлаа:\n{e}")

        threading.Thread(target=_do_rejoin, daemon=True).start()

    def action_stop_online_game(self):
        if not self.lobby_svc.active_room or not self.lobby_svc.is_host:
            return
        if messagebox.askyesno("Confirm", "Энэ тоглолтыг бүрэн дуусгаж хаах уу?"):
            self.engine.stop()
            self.lobby_svc.active_room["status"] = "Waiting in Lobby"
            self.lobby_svc.sig.publish(TOPIC_ROOMS, {
                "action": "update",
                "room_id": self.lobby_svc.active_room["room_id"],
                "status": "Waiting in Lobby"
            })
            self._build_active_room_panel()
            self.log("Host ended active match.")

    def action_leave_online_room(self):
        self.lobby_svc.leave_active_room()
        self.log("Left online room.")

    def on_close(self):
        if self.lobby_svc:
            self.lobby_svc.stop()
        if self.client_tunnel:
            self.client_tunnel.stop()
            self.client_tunnel = None
        self.warkey.stop()
        self.engine.stop()
        self.destroy()


def main():
    app = AegisApp()
    app.mainloop()


if __name__ == "__main__":
    main()
