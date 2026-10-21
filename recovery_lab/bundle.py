"""Stage an explicit game/client payload for local installer development."""
import argparse
import json
from pathlib import Path
import shutil

from .host import GAME
from .native_workspace import digest

GAME_FILES = ("war3.exe", "game.dll", "Storm.dll", "Mss32.dll", "ijl15.dll",
              "war3.mpq", "War3x.mpq", "War3xlocal.mpq", "War3Patch.mpq",
              "Maps/Download/DotA LoD 6.85m.w3x")


def stage(game: Path, client: Path, destination: Path):
    sources = [(game / name, Path("Game") / name) for name in GAME_FILES]
    sources.append((client, Path("Client/LoDClient.exe")))
    for source, _ in sources:
        if not source.is_file():
            raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError("Use a new staging directory; existing payloads are preserved")
    destination.mkdir(parents=True)
    records = []
    for source, relative in sources:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = digest(source)
        shutil.copy2(source, target)
        if digest(target) != expected:
            raise ValueError(f"Copy verification failed: {relative}")
        records.append({"path": relative.as_posix(), "sha256": expected, "size": target.stat().st_size})
    (destination / "manifest.json").write_text(json.dumps({
        "release_ready": False,
        "unresolved": ["native crash recovery", "two-player validation", "hotkey gameplay testing", "installer testing"],
        "files": records}, indent=2))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=GAME)
    parser.add_argument("--client", type=Path, default=Path("dist/LoDClient-Prototype.exe"))
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    records = stage(args.game, args.client, args.destination)
    print(json.dumps({"files": len(records), "bytes": sum(r["size"] for r in records), "release_ready": False}))


if __name__ == "__main__":
    main()
