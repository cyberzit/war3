"""Independently compare a reconstruction journal with pre-disconnect checksums."""
import argparse
import json
from pathlib import Path

from .protocol import checksum


def audit(source_rows, attempt_rows):
    expected = []
    for row in source_rows:
        if row.get("event") == "local_disconnected":
            break
        if row.get("direction") == "client":
            p = bytes.fromhex(row["packet"])
            if p[1] == 0x27:
                expected.append(checksum(p))
    starts = [i for i, row in enumerate(attempt_rows)
              if row.get("event") == "reconstruction_started"]
    actual = []
    failures = []
    after_completion = []
    verified = False
    started_at = attempt_rows[starts[-1]].get("time") if starts else None
    delivered_at = None
    delivered = False
    for row in attempt_rows[starts[-1] + 1:] if starts else []:
        event = row.get("event")
        if event in ("client_error", "reconstruction_failed"):
            (after_completion if verified else failures).append(row)
        if event == "transcript_delivered":
            delivered = True
            delivered_at = row.get("time")
        if row.get("direction") == "client":
            p = bytes.fromhex(row["packet"])
            if p[1] == 0x27:
                actual.append(checksum(p))
        if not verified and expected and delivered and not failures:
            verified = len(actual) >= len(expected) and actual[:len(expected)] == expected
    matched = 0
    mismatch = None
    for i, (wanted, got) in enumerate(zip(expected, actual)):
        if wanted != got:
            mismatch = i + 1
            break
        matched += 1
    return {"scope": "recorded checksums only; not live reconnect proof",
            "attempts": len(starts), "expected": len(expected),
            "received": len(actual), "matched": matched,
            "first_mismatch": mismatch, "transcript_delivered": delivered,
            "join_to_delivery_seconds": round(delivered_at - started_at, 3)
                if delivered_at is not None and started_at is not None else None,
            "failures": failures,
            "errors_after_completed_history": after_completion,
            "complete": bool(expected) and matched == len(expected)
                        and delivered and not failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path)
    parser.add_argument("--source", type=Path, default=Path("runtime/session.jsonl"))
    args = parser.parse_args()
    def rows(path):
        # A running writer may have an incomplete final line; only inspect
        # complete records, never repair or modify evidence files.
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        return [json.loads(line) for line in lines if line.endswith("\n")]
    print(json.dumps(audit(rows(args.source), rows(args.journal)), indent=2))


if __name__ == "__main__":
    main()
