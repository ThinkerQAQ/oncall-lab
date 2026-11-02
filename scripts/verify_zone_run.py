#!/usr/bin/env python3
"""Validate a three-phase synthetic zone fault-injection run from its JSON logs.

Only parse real loadgen output. The log remains local under ignored evidence/.
This proves the load generator saw distinct real Gateway endpoints; Docker
Compose and Prometheus provide separate proof of running Metadata processes.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from urllib.parse import urlsplit


def parse(log_text: str):
    observed = {}
    declared_total = None
    for line in log_text.splitlines():
        if not line.startswith("{"):
            continue
        entry = json.loads(line)
        if entry.get("msg") == "experiment observed requests":
            phase, zone, url = entry["phase_zone_target"].split("/", 2)
            gateway = urlsplit(url).hostname
            if not gateway:
                raise ValueError(f"missing gateway in {url!r}")
            key = phase, zone, gateway
            if key in observed:
                raise ValueError(f"duplicate experiment entry: {key}")
            observed[key] = entry["sent"], entry["failed"]
        elif entry.get("msg") == "synthetic zone experiment finished":
            declared_total = entry["total_requests"]
    return observed, declared_total


def verify(observed: dict, declared_total: int) -> dict:
    groups = defaultdict(lambda: [0, 0])
    gateways_seen = set()
    for (phase, zone, gateway), (sent, failed) in observed.items():
        if phase not in {"baseline", "incident", "recovery"}:
            raise ValueError(f"unexpected phase: {phase}")
        if zone not in {"zone-a", "zone-b", "zone-c"}:
            raise ValueError(f"unexpected zone: {zone}")
        if not gateway.startswith("gateway-" + zone):
            raise ValueError(f"gateway {gateway!r} does not belong to {zone}")
        if not isinstance(sent, int) or not isinstance(failed, int) or sent <= 0 or failed < 0 or failed > sent:
            raise ValueError(f"invalid counts for {gateway}")
        gateways_seen.add(gateway)
        groups[phase, zone][0] += sent
        groups[phase, zone][1] += failed
        if (phase != "incident" or zone != "zone-a") and failed:
            raise ValueError(f"unexpected failure in {phase}/{zone}/{gateway}")

    expected_gateways = {f"gateway-zone-{zone}{n}" for zone in "abc" for n in (1, 2)}
    if gateways_seen != expected_gateways:
        raise ValueError(f"missing or unexpected real gateways: {expected_gateways ^ gateways_seen}")
    expected_keys = {(phase, f"zone-{z}", f"gateway-zone-{z}{n}") for phase in ("baseline", "incident", "recovery") for z in "abc" for n in (1, 2)}
    if set(observed) != expected_keys:
        raise ValueError(f"missing or unexpected phase/zone/instance entries: {expected_keys ^ set(observed)}")
    if not all(observed[("incident", "zone-a", f"gateway-zone-a{n}")][1] > 0 for n in (1, 2)):
        raise ValueError("both zone-a gateways must independently observe timeout failures")
    total = sum(sent for sent, _ in observed.values())
    if total != declared_total:
        raise ValueError(f"request count mismatch: {total} != {declared_total}")
    return dict(sorted(groups.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="locally recorded loadgen JSON log")
    args = parser.parse_args()
    observed, total = parse(args.log.read_text())
    try:
        groups = verify(observed, total)
    except (ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    for (phase, zone), (requests, failures) in groups.items():
        print(f"{phase:9s} {zone:6s}  requests={requests:4d}  failures={failures:4d}")
    print(f"PASS: {total} requests, zone-a-only timeout failures distributed across two actual gateway instances")


if __name__ == "__main__":
    main()
