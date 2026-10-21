"""Configuration & Auto-Discovery Manager for Aegis Gaming Platform."""
import json
from pathlib import Path
import sys

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.json"

KNOWN_PATHS = [
    Path(r"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III"),
    Path(r"C:\Program Files (x86)\Warcraft III"),
    Path(r"C:\Program Files\Warcraft III"),
    Path(r"D:\Warcraft III"),
    Path(r"E:\Warcraft III"),
]


def load_config() -> dict:
    if CONFIG_FILE.is_file():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(data: dict):
    existing = load_config()
    existing.update(data)
    CONFIG_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def detect_warcraft_directory() -> Path:
    cfg = load_config()
    saved = cfg.get("game_path")
    if saved:
        p = Path(saved)
        if (p / "war3.exe").is_file():
            return p

    for candidate in KNOWN_PATHS:
        if (candidate / "war3.exe").is_file():
            save_config({"game_path": str(candidate)})
            return candidate

    return KNOWN_PATHS[0]


if __name__ == "__main__":
    p = detect_warcraft_directory()
    print("Detected Warcraft Directory:", p)
