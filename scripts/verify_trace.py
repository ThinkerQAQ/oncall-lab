#!/usr/bin/env python3
"""Verify one real three-level Kitex/HTTP trace returned by Tempo's trace API.

The trace must contain an HTTP gateway span, its Kitex client child, and a
Kitex server child in the Metadata process with consistent parent IDs.
"""
import argparse
import json
from pathlib import Path


def verify(data: dict):
    collected = []
    for batch in data.get("batches", []):
        attrs = batch.get("resource", {}).get("attributes", [])
        name = next(
            (a.get("value", {}).get("stringValue") for a in attrs if a.get("key") == "service.name"),
            None,
        )
        for group in batch.get("scopeSpans", []):
            for span in group.get("spans", []):
                collected.append((name, span))

    def only(service, span_name):
        matches = [
            span for name, span in collected
            if name == service and span.get("name") == span_name
        ]
        if len(matches) != 1:
            raise ValueError(f"expected one {service}/{span_name} span, found {len(matches)}")
        return matches[0]

    http = only("GatewayService", "HTTP GET /metadata")
    client = only("GatewayService", "metadata.MetadataService/GetMetadata")
    server = only("MetadataService", "metadata.MetadataService/GetMetadata")
    if client.get("parentSpanId") != http.get("spanId"):
        raise ValueError("Kitex client span is not a child of Gateway HTTP span")
    if server.get("parentSpanId") != client.get("spanId"):
        raise ValueError("Kitex server span is not a child of Kitex client span")
    ids = {span.get("traceId") for _, span in collected}
    if len(ids) != 1:
        raise ValueError("trace IDs disagree across HTTP and Kitex spans")
    return len(collected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_json", type=Path)
    args = parser.parse_args()
    try:
        count = verify(json.loads(args.trace_json.read_text()))
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(f"PASS: one correlated Gateway HTTP -> Kitex client -> Metadata server trace ({count} spans)")


if __name__ == "__main__":
    main()
