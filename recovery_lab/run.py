"""One-command runner for the local feasibility experiment, not a game platform."""
import argparse
import asyncio
from pathlib import Path
import time

from .host import GAME, create_room, launch, prepare, transfer_owner
from .protocol import join_game
from .proxy import LabProxy


async def assign_owner(proxy: LabProxy, player: str):
    while proxy.identity is None and not proxy.ended:
        await asyncio.sleep(0.25)
    if not proxy.ended:
        if proxy.identity[2].decode("ascii") != player:
            proxy.event("owner_name_mismatch", expected=player)
            return
        await asyncio.to_thread(transfer_owner, (Path("runtime") / "advertisement.bin").read_bytes(), player)
        proxy.event("owner_assigned", player=player)


async def run(advertisement: bytes, player: str):
    proxy = LabProxy(advertisement)
    owner = asyncio.create_task(assign_owner(proxy, player))
    try:
        await proxy.run()
    finally:
        owner.cancel()
        await asyncio.gather(owner, return_exceptions=True)


def main():
    parser = argparse.ArgumentParser(description="Warcraft III local reconstruction research lab")
    parser.add_argument("--game", type=Path, default=GAME)
    parser.add_argument("--player", required=True)
    parser.add_argument("--map", default=r"Maps\Download\LoD State Probe 7.w3x",
                        help="Research map path inside the game directory")
    args = parser.parse_args()
    join_game(0, 0, args.player)  # Validate before creating files or processes.
    runtime = prepare(args.game, args.map)
    for name in ("msvcp100.dll", "msvcr100.dll"):
        if not (runtime / name).is_file():
            raise SystemExit("Missing x86 VC++ 2010 runtime in runtime/host: " + name)
    process = launch(runtime)
    try:
        time.sleep(1)
        if process.poll() is not None:
            raise RuntimeError(f"Lab host exited with code {process.returncode}; see runtime/host/console.log")
        advertisement = create_room()
        Path("runtime/advertisement.bin").write_bytes(advertisement)
        asyncio.run(run(advertisement, args.player))
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()
