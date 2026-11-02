#!/usr/bin/env python3
"""Exercise a real Kubernetes rolling restart under concurrent Kitex RPC load.

This validates one single-host Kind cluster; no real physical AZs are involved.
No external traffic. Run after k8s/up.sh and local port-forward to 28084.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
KUBECTL = str(ROOT / "Data/bin/kubectl")
KUBECONFIG = str(ROOT / "Data/kind-kubeconfig")
NAMESPACE = "oncall-lab"
URL = "http://127.0.0.1:28084/metadata"
COUNT = 420
QPS = 10
INJECT_ROLLOUT_AFTER_REQUEST = 50


def run(*args):
    return subprocess.check_output([KUBECTL, "--kubeconfig", KUBECONFIG, "-n", NAMESPACE, *args], text=True).strip()


def send(index):
    start = time.monotonic()
    url = f"{URL}?id=rolling-{index}&delay_ms=900"
    code = None
    try:
        with urllib.request.urlopen(url, timeout=4.0) as response:
            code = response.status
            response.read()
    except urllib.error.HTTPError as error:
        code = error.code
    except Exception as error:
        code = f"client_exception:{type(error).__name__}"
    return {"sequence": index, "status": code, "elapsed_ms": round((time.monotonic()-start)*1000)}


def main():
    subprocess.run(["bash", "k8s/check.sh"], cwd=ROOT, check=True)
    try:
        with urllib.request.urlopen(f"{URL}?id=preflight", timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"preflight HTTP={response.status}")
    except Exception as exc:
        raise RuntimeError("start a scoped Kubernetes Gateway port-forward to 28084") from exc

    start = datetime.now(timezone.utc).isoformat()
    print("Running", COUNT, "real RPC calls at", QPS, "requests/s; each simulates 900ms work")
    futures = []
    rollout_started = None
    with ThreadPoolExecutor(max_workers=24) as pool:
        for i in range(COUNT):
            if i == INJECT_ROLLOUT_AFTER_REQUEST:
                rollout_started = datetime.now(timezone.utc).isoformat()
                print("REAL KUBERNETES ROLLING RESTART", rollout_started, flush=True)
                print(run("rollout", "restart", "deployment/metadata"), flush=True)
            futures.append(pool.submit(send, i))
            time.sleep(1/QPS)
        results = sorted((future.result() for future in as_completed(futures)), key=lambda item: item["sequence"])

    print(run("rollout", "status", "deployment/metadata", "--timeout=180s"))
    rollout_done = datetime.now(timezone.utc).isoformat()
    try:
        subprocess.run(["bash", "k8s/rebalance.sh"], cwd=ROOT, check=True)
        subprocess.run(["bash", "k8s/check.sh"], cwd=ROOT, check=True)
    finally:
        # Preserve actual results even if a topology assertion fails.
        output = ROOT / "evidence" / f"kube-rollout-with-rpc-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        output.parent.mkdir(exist_ok=True)
        statuses = {}
        for item in results:
            label = str(item["status"])
            statuses[label] = statuses.get(label, 0) + 1
        artifact = {
            "started_utc": start,
            "rollout_started_utc": rollout_started,
            "rollout_completed_utc": rollout_done,
            "planned_qps": QPS,
            "requested_delay_ms": 900,
            "request_count": len(results),
            "statuses": statuses,
            "requests": results,
            "environment": "single-host Kind, 6 Metadata pods; no real physical availability zones",
        }
        output.write_text(json.dumps(artifact, indent=2) + "\n")
        print("Recorded real results:", output)
        print("HTTP STATUS COUNTS:", statuses)
        assert len(results) == COUNT
        assert statuses.get("200", 0) > 0, "No successful Kitex requests observed"


if __name__ == "__main__":
    main()
