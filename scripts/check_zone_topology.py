#!/usr/bin/env python3
"""Validate that zone fault evidence comes from six real Kitex server containers.

Read the *rendered* Docker Compose JSON from stdin. No external Python packages.
"""
import json
import re
import sys
from pathlib import Path


def check(services: dict) -> None:
    expected_gateways = set()
    expected_metadata = set()
    for zone in "abc":
        for index in (1, 2):
            z = f"zone-{zone}"
            gateway = f"gateway-zone-{zone}{index}"
            metadata = f"metadata-zone-{zone}{index}"
            expected_gateways.add(gateway)
            expected_metadata.add(metadata)

            for service in (gateway, metadata):
                if service not in services:
                    raise ValueError(f"missing real container service: {service}")
                networks = services[service].get("networks", {})
                if z not in networks:
                    raise ValueError(f"{service} is not on isolated {z} network")

            address = services[gateway].get("environment", {}).get("METADATA_RPC_ADDR")
            if address != f"{metadata}:8888":
                raise ValueError(f"{gateway} calls {address!r}, expected {metadata}:8888")
            metadata_env = services[metadata].get("environment", {})
            if metadata_env.get("LAB_ZONE") != z:
                raise ValueError(f"{metadata} has wrong zone tag")
            if metadata_env.get("LAB_INSTANCE") != metadata:
                raise ValueError(f"{metadata} has wrong instance identity")

    zone_gateways = {k for k in services if re.fullmatch(r"gateway-zone-[abc]\d+", k)}
    zone_metadata = {k for k in services if re.fullmatch(r"metadata-zone-[abc]\d+", k)}
    if zone_gateways != expected_gateways:
        raise ValueError(f"unexpected Gateway set: {zone_gateways ^ expected_gateways}")
    if zone_metadata != expected_metadata:
        raise ValueError(f"unexpected Metadata set: {zone_metadata ^ expected_metadata}")

    # Scrape *each* concrete metadata instance, never a synthetic instance label.
    scrape_config = Path("observability/prometheus/prometheus-zones.yml").read_text()
    for metadata in expected_metadata:
        if f'"{metadata}:9091"' not in scrape_config:
            raise ValueError(f"Prometheus missing real backend {metadata}:9091")

    # Preserve one-to-one gateway -> metadata in this experiment only.
    # This demonstrates distribution across actual service processes.
    # It does NOT test a dynamic Kitex load-balancer or Kubernetes AZ topology.
    print("Verified six Gateway -> six Metadata Kitex processes across 3 synthetic Docker zones.")


if __name__ == "__main__":
    try:
        check(json.load(sys.stdin)["services"])
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Zone topology check failed: {exc}", file=sys.stderr)
        sys.exit(1)
