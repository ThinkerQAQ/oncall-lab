"""Pure unit tests for Kubernetes evidence validation; no cluster required."""
import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location("kind_check", Path(__file__).parent / "check.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def fixtures():
    nodes = {"items": []}
    pods = {"items": []}
    slices = {"items": [{"endpoints": []}]}
    for index, zone in enumerate(("a", "b", "c"), start=1):
        node = f"lab-worker-{index}"
        nodes["items"].append({
            "metadata": {"name": node, "labels": {"topology.kubernetes.io/zone": f"lab-zone-{zone}"}}
        })
        for number in (1, 2):
            ip = f"10.244.{index}.{number}"
            pods["items"].append({
                "metadata": {"name": f"metadata-{zone}{number}", "labels": {"app": "metadata"}},
                "spec": {"nodeName": node},
                "status": {"conditions": [{"type": "Ready", "status": "True"}], "podIP": ip},
            })
            slices["items"][0]["endpoints"].append({
                "addresses": [ip], "conditions": {"ready": True}
            })
    return nodes, pods, slices


class KindTopologyTest(unittest.TestCase):
    def test_real_pod_ips_and_three_zones(self):
        self.assertEqual(checker.verify(*fixtures()), {
            "lab-zone-a": 2, "lab-zone-b": 2, "lab-zone-c": 2,
        })

    def test_not_ready_endpoint_not_valid(self):
        nodes, pods, slices = fixtures()
        slices["items"][0]["endpoints"][0]["conditions"]["ready"] = False
        with self.assertRaises(ValueError):
            checker.verify(nodes, pods, slices)

    def test_fake_extra_pod_rejected(self):
        nodes, pods, slices = fixtures()
        pods["items"].append(pods["items"][0])
        with self.assertRaises(ValueError):
            checker.verify(nodes, pods, slices)

    def test_skips_terminating_old_revision(self):
        nodes, pods, slices = fixtures()
        stale = {
            "metadata": {"name": "stale", "labels": {"app": "metadata"}, "deletionTimestamp": "2026-01-01T00:00:00Z"},
            "spec": {"nodeName": "lab-worker-1"},
            "status": {"conditions": [{"type": "Ready", "status": "False"}], "podIP": "10.244.1.200"}
        }
        pods["items"].append(stale)
        self.assertEqual(sum(checker.verify(nodes, pods, slices).values()), 6)


if __name__ == "__main__":
    unittest.main()
