"""Preserve exact native inputs and separate working copies for binary research.

This stages binaries only, not a runnable game installation or a working patch.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from .host import GAME


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(source: Path, destination: Path) -> Path:
    names = ("war3.exe", "game.dll", "Storm.dll")
    records = []
    for name in names:
        original = source / name
        sha = digest(original)
        backup = destination / "originals" / sha / name
        working = destination / "working" / sha / name
        for target in (backup, working):
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(original, target)
            if digest(target) != sha:
                raise ValueError(f"Existing copy differs; refusing to overwrite: {target}")
        if digest(original) != sha:
            raise ValueError(f"Source changed while staging: {original}")
        records.append({"name": name, "sha256": sha, "size": original.stat().st_size,
                        "source": str(original.resolve()), "backup": str(backup.resolve()),
                        "working": str(working.resolve())})
    manifest = destination / "manifest.json"
    manifest.write_text(json.dumps({"status": "unmodified research copies", "files": records}, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=GAME)
    parser.add_argument("--destination", type=Path, default=Path("runtime/native"))
    args = parser.parse_args()
    print(prepare(args.game, args.destination))


if __name__ == "__main__":
    main()
