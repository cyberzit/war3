"""Launch the existing game as a child of the client for lifecycle diagnostics.

Does not elevate privileges, change compatibility settings, or modify game files.
"""
import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone

from .host import GAME


def existing_game_processes() -> list[int]:
    """Enumerate names without needing to open elevated game processes."""
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found = []
        success = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while success:
            if entry.szExeFile.lower() == "war3.exe":
                found.append(entry.th32ProcessID)
            success = kernel.Process32NextW(handle, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise ctypes.WinError(ctypes.get_last_error())
        return found
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description="Warcraft client lifecycle diagnostic")
    parser.add_argument("--game", type=Path, default=GAME)
    parser.add_argument("--seconds", type=int, default=30)
    args = parser.parse_args()
    output = Path("runtime") / datetime.now(timezone.utc).strftime("client-lifecycle-%Y%m%dT%H%M%S%fZ.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    existing = existing_game_processes()
    if existing:
        report = {"launch_succeeded": False, "existing_game_pids": existing,
                  "error": "Close existing Warcraft processes before a fresh-process diagnostic"}
        output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
        return
    try:
        process = subprocess.Popen([str(args.game / "war3.exe")], cwd=args.game,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        report = {"launch_succeeded": False, "error": str(exc),
                  "winerror": getattr(exc, "winerror", None)}
        output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
        return
    try:
        report = {"launch_succeeded": True, "pid": process.pid}
        time.sleep(2)
        report["initial_exit_code"] = process.poll()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x410, False, process.pid)  # query information + VM read only
        report["memory_query_access"] = bool(handle)
        report["memory_query_error"] = ctypes.get_last_error() if not handle else 0
        if handle:
            kernel.CloseHandle(ctypes.c_void_p(handle))
        # CreateProcess returns an existing handle to our own child. Query its
        # modules through that handle without requesting additional privileges.
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        modules = (ctypes.c_void_p * 1024)()
        needed = ctypes.c_ulong()
        owned = ctypes.c_void_p(int(process._handle))
        success = psapi.EnumProcessModulesEx(owned, modules, ctypes.sizeof(modules), ctypes.byref(needed), 3)
        report["owned_handle_module_query"] = bool(success)
        report["owned_handle_query_error"] = ctypes.get_last_error() if not success else 0
        if success:
            report["loaded_modules"] = []
            for module in modules[:needed.value // ctypes.sizeof(ctypes.c_void_p)]:
                name = ctypes.create_unicode_buffer(1024)
                psapi.GetModuleFileNameExW(owned, ctypes.c_void_p(module), name, len(name))
                report["loaded_modules"].append({"base": hex(module), "path": name.value})
                if name.value.lower().endswith("\\game.dll"):
                    probe = ctypes.create_string_buffer(2)
                    read = ctypes.c_size_t()
                    ok = kernel.ReadProcessMemory(owned, ctypes.c_void_p(module), probe, 2, ctypes.byref(read))
                    report["game_module_base"] = hex(module)
                    report["game_module_readable"] = bool(ok and probe.raw == b"MZ")
        output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
        process.wait(timeout=max(1, args.seconds))
    except subprocess.TimeoutExpired:
        pass
    finally:
        # Only the child launched by this diagnostic is terminated, using its
        # originally granted process handle. No unrelated process is targeted.
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()
