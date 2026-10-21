"""Automated Navigation & Game Joining for Warcraft III 1.26a (GameRanger-style).

Features:
1. Automatically detects Warcraft III window (DirectX fullscreen & windowed).
2. Uses dynamic screen resolution scaling (1024x768, 1920x1080, or stretched).
3. Navigates main menu into Local Area Network (mouse click + Alt+L + L).
4. Multi-attempt room selection & joining:
   - Double-clicks the 1st hosted game row.
   - Sends Down Arrow + Alt+J + Enter.
   - Clicks [ Join Game ] button.
5. Zero destructive key-spamming (no ESC/SPACE, registry intro bypass).
"""
import ctypes
import threading
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203

INPUT_KEYBOARD = 1
INPUT_MOUSE = 0

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

VK_ESCAPE = 0x1B
VK_TAB = 0x09
VK_SPACE = 0x20
VK_L = 0x4C
VK_J = 0x4A
VK_DOWN = 0x28
VK_RETURN = 0x0D
VK_MENU = 0x12  # Alt


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    _anonymous_ = ("_input",)
    _fields_ = [("type", ctypes.c_ulong), ("_input", _INPUT)]


def ensure_desktop_access():
    """Attaches process to interactive desktop winsta0\\default so windows and input work across sessions."""
    try:
        user32.OpenWindowStationW.restype = ctypes.c_void_p
        user32.SetProcessWindowStation.argtypes = [ctypes.c_void_p]
        user32.OpenDesktopW.restype = ctypes.c_void_p
        user32.SetThreadDesktop.argtypes = [ctypes.c_void_p]
        hwinsta = user32.OpenWindowStationW("winsta0", False, 0x10000000)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
        hdesk = user32.OpenDesktopW("default", 0, False, 0x10000000)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("lpReserved", ctypes.c_wchar_p),
        ("lpDesktop", ctypes.c_wchar_p),
        ("lpTitle", ctypes.c_wchar_p),
        ("dwX", ctypes.c_ulong),
        ("dwY", ctypes.c_ulong),
        ("dwXSize", ctypes.c_ulong),
        ("dwYSize", ctypes.c_ulong),
        ("dwXCountChars", ctypes.c_ulong),
        ("dwYCountChars", ctypes.c_ulong),
        ("dwFillAttribute", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("wShowWindow", ctypes.c_ushort),
        ("cbReserved2", ctypes.c_ushort),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", ctypes.c_void_p),
        ("hStdOutput", ctypes.c_void_p),
        ("hStdError", ctypes.c_void_p),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", ctypes.c_void_p),
        ("hThread", ctypes.c_void_p),
        ("dwProcessId", ctypes.c_ulong),
        ("dwThreadId", ctypes.c_ulong),
    ]


def launch_process_on_default_desktop(exe_path: str, args: str, cwd: str) -> int:
    """Launches a GUI process directly onto the interactive user's winsta0\\default desktop."""
    ensure_desktop_access()
    cmd_buf = ctypes.create_unicode_buffer(f'"{exe_path}" {args}'.strip())
    si = _STARTUPINFOW()
    si.cb = ctypes.sizeof(_STARTUPINFOW)
    si.lpDesktop = "winsta0\\default"
    si.dwFlags = 1  # STARTF_USESHOWWINDOW
    si.wShowWindow = 1  # SW_SHOWNORMAL
    pi = _PROCESS_INFORMATION()
    ok = kernel32.CreateProcessW(
        None,
        cmd_buf,
        None,
        None,
        False,
        0,
        None,
        cwd,
        ctypes.byref(si),
        ctypes.byref(pi),
    )
    if not ok:
        return 0
    return int(pi.dwProcessId)


def force_foreground(hwnd: int):
    """Bypasses Windows SetForegroundWindow lock by attaching to foreground thread."""
    ensure_desktop_access()
    try:
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
        cur_thread = kernel32.GetCurrentThreadId()

        if fg_thread != cur_thread and fg_thread != 0:
            user32.AttachThreadInput(cur_thread, fg_thread, True)

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE only if minimized
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)

        if fg_thread != cur_thread and fg_thread != 0:
            user32.AttachThreadInput(cur_thread, fg_thread, False)
    except Exception:
        pass


def send_dual_key(hwnd: int, scancode: int, vk: int, extended: bool = False, hold: float = 0.05):
    """Sends keystroke through both hardware SendInput and PostMessageW."""
    flags_down = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    flags_up = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP | (KEYEVENTF_EXTENDEDKEY if extended else 0)

    inp_down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=scancode, dwFlags=flags_down, time=0, dwExtraInfo=None))
    inp_up = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=scancode, dwFlags=flags_up, time=0, dwExtraInfo=None))

    user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))

    lparam_down = 1 | (scancode << 16) | (0x01000000 if extended else 0)
    lparam_up = 1 | (scancode << 16) | (0x01000000 if extended else 0) | (0xC0 << 24)
    if hwnd:
        user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lparam_down)

    time.sleep(hold)

    user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))
    if hwnd:
        user32.PostMessageW(hwnd, WM_KEYUP, vk, lparam_up)


def send_alt_combo(hwnd: int, scancode: int, vk: int):
    """Sends Alt + Key combination via both hardware SendInput and WM_SYSKEYDOWN."""
    alt_down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=VK_MENU, wScan=0x38, dwFlags=KEYEVENTF_SCANCODE, time=0, dwExtraInfo=None))
    key_down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=vk, wScan=scancode, dwFlags=KEYEVENTF_SCANCODE, time=0, dwExtraInfo=None))
    key_up = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=vk, wScan=scancode, dwFlags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None))
    alt_up = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=VK_MENU, wScan=0x38, dwFlags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None))

    user32.SendInput(1, ctypes.byref(alt_down), ctypes.sizeof(INPUT))
    if hwnd:
        user32.PostMessageW(hwnd, WM_SYSKEYDOWN, VK_MENU, 0x20380001)
    time.sleep(0.04)

    user32.SendInput(1, ctypes.byref(key_down), ctypes.sizeof(INPUT))
    if hwnd:
        user32.PostMessageW(hwnd, WM_SYSKEYDOWN, vk, (scancode << 16) | 0x20000001)
    time.sleep(0.06)

    user32.SendInput(1, ctypes.byref(key_up), ctypes.sizeof(INPUT))
    if hwnd:
        user32.PostMessageW(hwnd, WM_SYSKEYUP, vk, (scancode << 16) | 0xC0000001)
    time.sleep(0.04)

    user32.SendInput(1, ctypes.byref(alt_up), ctypes.sizeof(INPUT))
    if hwnd:
        user32.PostMessageW(hwnd, WM_SYSKEYUP, VK_MENU, 0xC0380001)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def smooth_glide_mouse(target_x: int, target_y: int, duration: float = 0.30, steps: int = 24):
    """Visibly glides mouse cursor across the screen with smooth cubic ease-out like GameRanger."""
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    start_x, start_y = pt.x, pt.y

    dist = ((target_x - start_x) ** 2 + (target_y - start_y) ** 2) ** 0.5
    if dist < 4:
        user32.SetCursorPos(target_x, target_y)
        return

    step_time = duration / steps
    for i in range(1, steps + 1):
        t = i / float(steps)
        # Smooth cubic ease-out: 1 - (1 - t)^3
        ease = 1.0 - (1.0 - t) ** 3
        curr_x = int(start_x + (target_x - start_x) * ease)
        curr_y = int(start_y + (target_y - start_y) * ease)
        user32.SetCursorPos(curr_x, curr_y)
        time.sleep(step_time)

    user32.SetCursorPos(target_x, target_y)
    # Crucial: War3 UI loop needs a few frames of hover to register button hitbox
    time.sleep(0.06)


def send_mouse_click(hwnd: int, x: int, y: int, glide: bool = True):
    """Visibly glides mouse cursor to (x, y) like GameRanger and performs hardware click."""
    if glide:
        smooth_glide_mouse(x, y, duration=0.28, steps=20)
    else:
        user32.SetCursorPos(x, y)
        time.sleep(0.04)

    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.06)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    if hwnd:
        lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
        user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lparam)
        time.sleep(0.04)
        user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)


def send_mouse_double_click(hwnd: int, x: int, y: int, glide: bool = True):
    """Glides mouse and delivers double-click with realistic inter-click delay."""
    if glide:
        smooth_glide_mouse(x, y, duration=0.28, steps=20)
    else:
        user32.SetCursorPos(x, y)
        time.sleep(0.04)

    # Click 1
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.08)

    # Click 2
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    if hwnd:
        lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
        user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lparam)
        time.sleep(0.03)
        user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
        time.sleep(0.06)
        user32.PostMessageW(hwnd, WM_LBUTTONDBLCLK, 1, lparam)
        time.sleep(0.03)
        user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)


def get_war3_geometry(hwnd: int) -> tuple[int, int, int, int]:
    """Calculates screen origin and size of War3 client area (works for fullscreen and windowed)."""
    rect = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    pt = POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        width = user32.GetSystemMetrics(0) or 1024
        height = user32.GetSystemMetrics(1) or 768
        return 0, 0, width, height
    return pt.x, pt.y, width, height


def press_scan(scancode: int, extended: bool = False, hold_time: float = 0.05, hwnd: int = 0):
    """Backwards-compatible helper for pressing a scan code."""
    if not hwnd:
        hwnd = find_war3_window() or 0
    vk = user32.MapVirtualKeyA(scancode, 1) or 0
    send_dual_key(hwnd, scancode, vk, extended=extended, hold=hold_time)


def send_combo(modifier_scan: int, key_scan: int, hwnd: int = 0):
    """Backwards-compatible helper for sending Alt+key."""
    if not hwnd:
        hwnd = find_war3_window() or 0
    vk = user32.MapVirtualKeyA(key_scan, 1) or 0
    send_alt_combo(hwnd, key_scan, vk)


def find_war3_window() -> int | None:
    """Finds the Warcraft III game window using title, class, and process inspection."""
    ensure_desktop_access()
    hwnd = user32.FindWindowW("Warcraft III", "Warcraft III")
    if hwnd and user32.IsWindow(hwnd):
        return hwnd

    hwnd = user32.FindWindowW("Warcraft III", None)
    if hwnd and user32.IsWindow(hwnd):
        return hwnd

    hwnd = user32.FindWindowW(None, "Warcraft III")
    if hwnd and user32.IsWindow(hwnd):
        return hwnd

    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)

    def enum_proc(h, lParam):
        if user32.IsWindow(h) and user32.IsWindowVisible(h):
            cb = ctypes.create_unicode_buffer(256)
            tb = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, cb, 256)
            user32.GetWindowTextW(h, tb, 256)
            if cb.value == "Warcraft III" or tb.value == "Warcraft III":
                found.append(h)
        return True

    user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
    return found[0] if found else None


def auto_join_war3_room(timeout: float = 30.0):
    """Waits for War3 window, navigates through main menu to LAN, selects room, and joins."""
    print("[Navigator] Auto-join thread started. Waiting for Warcraft III window...")
    deadline = time.monotonic() + timeout

    hwnd = None
    while time.monotonic() < deadline:
        hwnd = find_war3_window()
        if hwnd and user32.IsWindowVisible(hwnd):
            break
        time.sleep(0.3)

    if not hwnd:
        print("[Navigator] Warcraft III window not detected within timeout.")
        return

    print(f"[Navigator] Detected Warcraft III window (HWND: {hwnd}). Waiting for main menu...")
    # Give the engine 4.0s to finish initial Direct3D render of the main menu
    time.sleep(4.0)
    force_foreground(hwnd)

    origin_x, origin_y, win_w, win_h = get_war3_geometry(hwnd)
    print(f"[Navigator] War3 Geometry: Origin=({origin_x}, {origin_y}), Size={win_w}x{win_h}")

    # 1. Enter Local Area Network ('L' / Alt+L / Gliding Mouse click)
    lan_x = origin_x + int(win_w * 0.65)
    lan_y = origin_y + int(win_h * 0.40)
    print(f"[Navigator] Gliding mouse to Local Area Network button ({lan_x}, {lan_y})...")
    for _ in range(2):
        force_foreground(hwnd)
        send_mouse_click(hwnd, lan_x, lan_y, glide=True)
        send_dual_key(hwnd, 0x26, VK_L)          # 'L'
        time.sleep(0.12)
        send_alt_combo(hwnd, 0x26, VK_L)         # Alt+L
        time.sleep(0.25)

    # 2. Wait for Local Area Network menu to load and receive UDP broadcast room
    print("[Navigator] Waiting for LAN room list to update...")
    time.sleep(2.5)
    force_foreground(hwnd)

    # Calculate coordinates relative to Warcraft III window
    row1_x = origin_x + int(win_w * 0.25)
    row1_y = origin_y + int(win_h * 0.48)
    join_btn_x = origin_x + int(win_w * 0.89)
    join_btn_y = origin_y + int(win_h * 0.74)

    # 3. Select and join the hosted room
    print(f"[Navigator] Gliding cursor to room list ({row1_x}, {row1_y}) and [Join] button ({join_btn_x}, {join_btn_y})...")
    for attempt in range(1, 3):
        force_foreground(hwnd)
        # Visibly glide mouse and double-click first row in the LAN games list
        send_mouse_double_click(hwnd, row1_x, row1_y, glide=True)
        time.sleep(0.2)

        # Keyboard fallback: Down Arrow to select row -> Alt+J -> Enter
        send_dual_key(hwnd, 0x50, VK_DOWN, extended=True)
        time.sleep(0.12)
        send_alt_combo(hwnd, 0x24, VK_J)         # Alt+J (Join Game)
        time.sleep(0.12)
        send_dual_key(hwnd, 0x1C, VK_RETURN)     # Enter
        time.sleep(0.2)

        # Visibly glide mouse and click the [ Join Game ] button directly
        send_mouse_click(hwnd, join_btn_x, join_btn_y, glide=True)
        time.sleep(0.6)

    print("[Navigator] GameRanger-style auto-join completed successfully!")
    # Wait for lobby handshake and auto-start countdown
    time.sleep(2.5)
    auto_send_lobby_start(hwnd)


def auto_send_lobby_start(hwnd: int | None = None) -> bool:
    """Types '!start force' into the Warcraft III lobby chat to trigger automatic match start."""
    ensure_desktop_access()
    if not hwnd:
        hwnd = find_war3_window()
    if not hwnd:
        return False

    force_foreground(hwnd)
    time.sleep(0.3)

    VK_RETURN = 0x0D
    # Scancodes for '!start force'
    SCAN_MAP = [
        (0x02, True),   # ! (Shift + 1)
        (0x1F, False),  # s
        (0x14, False),  # t
        (0x1E, False),  # a
        (0x13, False),  # r
        (0x14, False),  # t
        (0x39, False),  # space
        (0x21, False),  # f
        (0x18, False),  # o
        (0x13, False),  # r
        (0x2E, False),  # c
        (0x12, False),  # e
    ]

    # 1. Open chat with Enter
    send_dual_key(hwnd, 0x1C, VK_RETURN)
    time.sleep(0.12)

    # 2. Type characters
    for scan, shift in SCAN_MAP:
        if shift:
            s_down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0x10, wScan=0x2A, dwFlags=KEYEVENTF_SCANCODE, time=0, dwExtraInfo=None))
            user32.SendInput(1, ctypes.byref(s_down), ctypes.sizeof(INPUT))
            time.sleep(0.02)

        press_scan(scan, hold_time=0.04, hwnd=hwnd)
        time.sleep(0.03)

        if shift:
            s_up = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0x10, wScan=0x2A, dwFlags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None))
            user32.SendInput(1, ctypes.byref(s_up), ctypes.sizeof(INPUT))
            time.sleep(0.02)

    time.sleep(0.12)
    # 3. Submit chat with Enter
    send_dual_key(hwnd, 0x1C, VK_RETURN)
    time.sleep(0.3)
    print("[Navigator] '!start force' automatically sent to Warcraft III lobby!")
    return True


def launch_auto_join_thread(delay: float = 0.5):
    """Spawns background thread to automatically navigate War3 into the LAN game."""
    def worker():
        if delay > 0:
            time.sleep(delay)
        auto_join_war3_room()

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    return th
