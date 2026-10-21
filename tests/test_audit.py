import unittest

from recovery_lab.audit import audit
from recovery_lab.protocol import packet


def check(value):
    return {"direction": "client", "packet": packet(0x27, b"\0" + value).hex()}


class AuditTests(unittest.TestCase):
    def test_latest_attempt_and_original_disconnect_boundary(self):
        source = [check(b"abcd"), {"event": "local_disconnected"}, check(b"xxxx")]
        attempt = [{"event": "reconstruction_started"}, check(b"xxxx"),
                   {"event": "client_error"}, {"event": "reconstruction_started"},
                   check(b"abcd"), {"event": "transcript_delivered"}]
        result = audit(source, attempt)
        self.assertTrue(result["complete"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["expected"], 1)

    def test_mismatch_cannot_be_hidden_by_delivery_event(self):
        result = audit([check(b"abcd"), check(b"efgh")],
                       [{"event": "reconstruction_started"}, check(b"abcd"),
                        check(b"xxxx"), {"event": "transcript_delivered"}])
        self.assertFalse(result["complete"])
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["first_mismatch"], 2)

    def test_empty_partial_and_failed_runs_are_not_complete(self):
        start = {"event": "reconstruction_started"}
        done = {"event": "transcript_delivered"}
        self.assertFalse(audit([], [start, done])["complete"])
        self.assertFalse(audit([check(b"abcd")], [start, done])["complete"])
        self.assertFalse(audit([check(b"abcd")], [start, check(b"abcd")])["complete"])
        self.assertFalse(audit([check(b"abcd")], [start, check(b"abcd"),
                         {"event": "client_error"}, done])["complete"])

    def test_later_teardown_is_reported_separately(self):
        result = audit([check(b"abcd")], [{"event": "reconstruction_started"},
                       check(b"abcd"), {"event": "transcript_delivered"},
                       {"event": "client_error", "detail": "test process terminated"}])
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["errors_after_completed_history"]), 1)
