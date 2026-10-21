"""Own exact test-process handles for repeatable forced-crash experiments.

Control files name both instance and PID. Never kills by executable name.
No automatic recovery claim: restarting only opens Warcraft's main menu.
"""
import json
from pathlib import Path
import subprocess
import time
import importlib
import argparse
import lab_memory_snapshot

LAB = Path(__file__).resolve().parents[1] / 'runtime/two-client-lab'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', choices=('A', 'B'))
    args = parser.parse_args()
    children = {}
    for label in ((args.only,) if args.only else ('A', 'B')):
        children[label] = subprocess.Popen([str(LAB / label / 'war3.exe'), '-window'], cwd=LAB / label)
    print({k: p.pid for k, p in children.items()}, flush=True)
    state_name = f'owned-client-{args.only}.json' if args.only else 'owned-clients.json'
    (LAB / state_name).write_text(json.dumps({k: p.pid for k, p in children.items()}))
    deadline = time.monotonic() + 3600
    while time.monotonic() < deadline and any(p.poll() is None for p in children.values()):
        for label, child in children.items():
            inspect = LAB / f'inspect-{label}-{child.pid}.request'
            if inspect.exists() and child.poll() is None:
                try:
                    # Reload only this local development diagnostic between requests.
                    result = importlib.reload(lab_memory_snapshot).snapshot(int(child._handle))
                except Exception as exc:
                    result = {'error': str(exc)}
                (LAB / f'inspect-{label}-{child.pid}.json').write_text(json.dumps(result, indent=2))
                inspect.unlink()
            marker = LAB / f'force-crash-{label}-{child.pid}.request'
            if marker.exists() and child.poll() is None:
                child.kill()
                child.wait(timeout=10)
                print(f'Forced crash {label} PID {child.pid}: exit {child.returncode}', flush=True)
        time.sleep(0.25)
    print('Controller ended; remaining clients left running.', flush=True)


if __name__ == '__main__':
    main()
