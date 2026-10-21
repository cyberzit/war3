"""Fail-closed checksum gate for experimental reconstruction of a fresh client."""
from .protocol import checksum


class SyncMismatch(ValueError):
    pass


class SyncGate:
    def __init__(self):
        self.history: list[bytes] = []
        self.replaying = False
        self.cursor = 0

    def restart(self):
        if not self.history:
            raise ValueError("No verified simulation history to reconstruct")
        self.cursor = 0
        self.replaying = True

    def accept(self, data: bytes) -> bool:
        value = checksum(data)
        if self.replaying and self.cursor < len(self.history):
            if value != self.history[self.cursor]:
                raise SyncMismatch(f"Simulation differs at checkpoint {self.cursor + 1}")
            self.cursor += 1
            # This is only a necessary condition, not a complete proof of state.
            # Do not duplicate old acknowledgments on the server connection.
            return False
        self.replaying = False
        self.history.append(value)
        return True
