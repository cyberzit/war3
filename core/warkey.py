"""Warcraft III foreground key remapper.

Architecture:
- 64-bit clean LRESULT / WPARAM / LPARAM hook callback.
- STRICT foreground check: Hook ONLY acts when active window is Warcraft III.
- Outside Warcraft III: pass keys through; release previously injected held keys.
- Inside Warcraft III:
  * Chat tracking: Enter toggles chat mode; Esc cancels chat.
  * In chat mode: all keys pass through cleanly so typing is unaffected.
  * Outside chat: ONLY specifically configured keys are remapped to Inventory or Skills.
  * All non-configured keys pass through natively (Attack, Stop, Hold, Control groups, etc.).
  * SendInput uses the complete native INPUT structure and non-extended numpad keys.
"""
import ctypes
from ctypes import wintypes
import threading
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Win32 Constants
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001

# Virtual Key Codes
VK_NUMPAD7 = 0x67
VK_NUMPAD8 = 0x68
VK_NUMPAD4 = 0x64
VK_NUMPAD5 = 0x65
VK_NUMPAD1 = 0x61
VK_NUMPAD2 = 0x62
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_CONTROL = 0x11
VK_F5 = 0x74

AEGIS_EXTRA_INFO = 0xAE615


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]
    _anonymous_ = ("_input",)
    _fields_ = [("type", wintypes.DWORD), ("_input", _INPUT)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


# 64-bit clean LRESULT callback signature
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

# Explicit Win32 function signatures for 64-bit stability
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK

user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t

user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL


user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = ctypes.c_ssize_t


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL
_process_cache = (None, 0.0, None)


def process_name(pid):
    """Read process identity without opening the game's protected process handle."""
    global _process_cache
    now = time.monotonic()
    if _process_cache[0] == pid and now < _process_cache[1]:
        return _process_cache[2]
    snapshot = kernel32.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (None, ctypes.c_void_p(-1).value):
        raise OSError("Windows process list could not be read.")
    name = None
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            if entry.th32ProcessID == pid:
                name = entry.szExeFile.lower()
                break
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    _process_cache = (pid, now + 0.5, name)
    return name


def war3_foreground():
    """Require both the Warcraft window class and its actual process identity."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, cls, len(cls))
    if cls.value != "Warcraft III":
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if process_name(pid.value) != "war3.exe":
        return None
    return (int(hwnd), pid.value)


def is_war3_foreground():
    return war3_foreground() is not None


def send_hardware_scancode(vk_code: int, key_up: bool = False):
    """Inject a marked key event; report whether Windows accepted it."""
    scan = user32.MapVirtualKeyW(vk_code, 0)
    flags = (KEYEVENTF_KEYUP if key_up else 0)

    inp = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(
            wVk=vk_code,
            wScan=scan,
            dwFlags=flags,
            time=0,
            dwExtraInfo=AEGIS_EXTRA_INFO,
        ),
    )
    return user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1


class AegisWarKey:
    def __init__(self, inv_mapping: dict | None = None, skill_mapping: dict | None = None):
        self.inv_mapping = dict(inv_mapping or {})
        self.skill_mapping = dict(skill_mapping or {})
        self.enabled = True
        self.chat_active = False
        self.hook_id = None
        self.hook_proc = None
        self.thread = None
        self._thread_id = None
        self._game = None
        self._down = set()
        self._held = {}
        self._ready = threading.Event()
        self.last_error = None

    @property
    def mapping(self):
        return self.inv_mapping

    @mapping.setter
    def mapping(self, val):
        self.inv_mapping = dict(val or {})

    def _release_held(self):
        for target in set(self._held.values()):
            send_hardware_scancode(target, key_up=True)
        self._held.clear()

    def _hook_callback(self, nCode, wParam, lParam):
        try:
            return self._handle_key(nCode, wParam, lParam)
        except Exception as exc:
            # Never let a callback error swallow the user's keyboard.
            self.last_error = str(exc)
            return user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)

    def _handle_key(self, nCode, wParam, lParam):
        def passthrough():
            return user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)
        if nCode < 0 or wParam not in (WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP):
            return passthrough()
        kbd = KBDLLHOOKSTRUCT.from_address(lParam)
        if kbd.dwExtraInfo == AEGIS_EXTRA_INFO:
            return passthrough()
        vk = kbd.vkCode
        down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
        game = war3_foreground()
        if not game or not self.enabled:
            self._release_held()
            self._down.clear()
            # Alt-Tab does not close Warcraft's chat. Preserve its state.
            return passthrough()
        if game != self._game:
            self._release_held()
            self._game = game
            self.chat_active = False
            self._down.clear()
        repeated = vk in self._down
        if down:
            self._down.add(vk)
        else:
            self._down.discard(vk)
        # Release the original target even if mappings/chat changed mid-press.
        if not down and vk in self._held:
            send_hardware_scancode(self._held.pop(vk), key_up=True)
            return 1
        system_chord = any(user32.GetAsyncKeyState(key) & 0x8000
                           for key in (0x12, 0x5B, 0x5C))
        if vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5) or system_chord:
            self._release_held()
            return passthrough()
        if vk == VK_RETURN:
            if down:
                if repeated:
                    return 1
                self._release_held()
                self.chat_active = not self.chat_active
            return passthrough()
        if vk == VK_ESCAPE:
            if down:
                self._release_held()
                self.chat_active = False
            return passthrough()
        if user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
            self._release_held()
            return passthrough()
        if self.chat_active:
            return passthrough()
        target = self._held.get(vk, self.inv_mapping.get(vk, self.skill_mapping.get(vk)))
        if target and target != vk and down:
            if send_hardware_scancode(target):
                self.last_error = None
                self._held[vk] = target
                return 1
            self.last_error = "Товч дамжуулах эрх хүрэлцэхгүй байна. Warcraft админ эрхтэй бол MongolRanger-ийг мөн Run as administrator-аар нээнэ үү."
        return passthrough()

    def _run_hook_loop(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        self.hook_proc = HOOKPROC(self._hook_callback)
        self.hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self.hook_proc,
            0,
            0,
        )
        if not self.hook_id:
            self.last_error = "Keyboard hook could not start."
            self._ready.set()
            print("[WarKey] Failed to install keyboard hook. Error:", ctypes.GetLastError())
            return

        self._ready.set()
        print("[WarKey] Keyboard hook active. Listening for Warcraft III...")
        msg = wintypes.MSG()
        while self.hook_id:
            b_ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if b_ret == 0 or b_ret == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        self._release_held()
        if self.hook_id:
            user32.UnhookWindowsHookEx(self.hook_id)
            self.hook_id = None
        print("[WarKey] Keyboard hook uninstalled.")

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self._ready.clear()
        self.enabled = True
        self.thread = threading.Thread(target=self._run_hook_loop, daemon=True)
        self.thread.start()
        self._ready.wait(timeout=2)

    def stop(self):
        if self._thread_id and self.thread and self.thread.is_alive():
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
            self.thread.join(timeout=2)
        if not self.thread or not self.thread.is_alive():
            self.thread = None
            self._thread_id = None
            self.enabled = False
