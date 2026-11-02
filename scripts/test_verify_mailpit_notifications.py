import unittest
from datetime import datetime, timezone

from verify_mailpit_notifications import verify


def message(status, address="oncall@example.test"):
    return {
        "Subject": f"[{status}] Synthetic Zone A Kitex RPC timeout rate",
        "To": [{"Address": address}],
    }


class VerifyEmailNotificationTests(unittest.TestCase):
    def test_firing_and_resolved(self):
        result = verify({"messages": [
            message("FIRING:1"), message("RESOLVED")
        ]})
        self.assertEqual(set(result), {"firing", "resolved"})

    def test_refuses_missing_recovery(self):
        with self.assertRaises(ValueError):
            verify({"messages": [message("FIRING:1")]})

    def test_refuses_external_recipient(self):
        with self.assertRaises(ValueError):
            verify({"messages": [
                message("FIRING:1", "someone@gmail.com"),
                message("RESOLVED"),
            ]})

    def test_ignores_old_deliveries(self):
        old = message("FIRING:1")
        old["Created"] = "2026-10-31T00:00:00Z"
        new = message("RESOLVED")
        new["Created"] = "2026-11-02T00:00:00Z"
        with self.assertRaises(ValueError):
            verify({"messages": [old, new]}, since=datetime(2026, 11, 1, tzinfo=timezone.utc))

    def test_firing_only_mode(self):
        self.assertEqual(
            set(verify({"messages": [message("FIRING:1")]}, require_recovery=False)),
            {"firing"},
        )


if __name__ == "__main__":
    unittest.main()
