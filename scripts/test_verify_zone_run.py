import unittest

from verify_zone_run import verify


def fixture():
    observed = {}
    for phase in ("baseline", "incident", "recovery"):
        for zone in "abc":
            for i in (1, 2):
                observed[phase, f"zone-{zone}", f"gateway-zone-{zone}{i}"] = (100, 10 if phase == "incident" and zone == "a" else 0)
    return observed


class ZoneRunVerificationTests(unittest.TestCase):
    def test_valid_zone_a_only_incident(self):
        rows = verify(fixture(), 1800)
        self.assertEqual(rows[("incident", "zone-a")], [200, 20])

    def test_refuses_missing_instance(self):
        x = fixture()
        del x[("incident", "zone-a", "gateway-zone-a2")]
        with self.assertRaises(ValueError):
            verify(x, 1700)

    def test_refuses_failure_outside_zone_a(self):
        x = fixture()
        x[("incident", "zone-b", "gateway-zone-b1")] = (100, 1)
        with self.assertRaises(ValueError):
            verify(x, 1800)

    def test_refuses_failure_during_recovery(self):
        x = fixture()
        x[("recovery", "zone-a", "gateway-zone-a1")] = (100, 1)
        with self.assertRaises(ValueError):
            verify(x, 1800)

    def test_refuses_count_mismatch(self):
        with self.assertRaises(ValueError):
            verify(fixture(), 1799)


if __name__ == "__main__":
    unittest.main()
