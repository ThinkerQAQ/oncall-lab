from datetime import datetime, timezone
import unittest
from verify_mailpit_notifications import verify


def message(priority, state, address="oncall@example.test", created="2026-11-02T00:00:00Z"):
    sev = {"P1": "CRITICAL", "P2": "WARNING"}[priority]
    return {
        "Subject": f"[{state}][{priority}][{sev}] Synthetic Zone A Kitex RPC alert",
        "To": [{"Address": address}],
        "Created": created,
    }


def both():
    return {"messages": [
        message("P1", "FIRING"), message("P1", "RESOLVED"),
        message("P2", "FIRING"), message("P2", "RESOLVED")
    ]}


class NotificationVerificationTests(unittest.TestCase):
    def test_firing_and_recovery_for_two_levels(self):
        self.assertEqual(len(verify(both())), 4)

    def test_refuses_missing_p1_recovery(self):
        sample = both()
        sample["messages"].pop(1)
        with self.assertRaises(ValueError):
            verify(sample)

    def test_refuses_wrong_priority_severity(self):
        sample = both()
        sample["messages"][0]["Subject"] = "[FIRING][P1][WARNING] Synthetic Zone A Kitex RPC alert"
        with self.assertRaises(ValueError):
            verify(sample)

    def test_refuses_external_recipient(self):
        sample = both()
        sample["messages"][0]["To"] = [{"Address": "unknown@example.org"}]
        with self.assertRaises(ValueError):
            verify(sample)

    def test_firing_only(self):
        sample = both()
        sample["messages"] = [sample["messages"][0], sample["messages"][2]]
        self.assertEqual(len(verify(sample, require_recovery=False)), 2)

    def test_since_excludes_previous_delivery(self):
        with self.assertRaises(ValueError):
            verify(both(), since=datetime(2026, 11, 3, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
