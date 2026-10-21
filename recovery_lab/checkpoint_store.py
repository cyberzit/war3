"""Stage a validated checkpoint under a short, shared Warcraft filename.

The original GHost autosave name was invisible to the 1.26a load browser;
identical bytes under checkpoint.w3z were recognized and joined successfully.
This fixes discovery only, not world restoration or live reattachment.
"""
import hashlib
import os
from pathlib import Path
import tempfile

from recovery_lab.save_checkpoint import inspect_save


def stage_checkpoint(source: Path, destination: Path) -> Path:
    """Publish complete bytes atomically; never overwrite another checkpoint."""
    destination.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.checkpoint-', suffix='.tmp', dir=destination)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, 'wb') as output, source.open('rb') as incoming:
            total = 0
            while chunk := incoming.read(65536):
                total += len(chunk)
                if total > 64 * 1024 * 1024:
                    raise ValueError('Checkpoint exceeds size limit')
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        report = inspect_save(temporary)
        target = destination / ('mr_' + report['sha256'][:20] + '.w3z')
        # Hard-link publication is atomic and fails if the name already exists.
        # Both files are in the same directory/filesystem.
        try:
            os.link(temporary, target)
        except FileExistsError:
            if hashlib.sha256(target.read_bytes()).hexdigest() != report['sha256']:
                raise ValueError('Checkpoint filename collision; existing file preserved')
        return target
    finally:
        temporary.unlink(missing_ok=True)
