#!/usr/bin/env python3
"""Require two real Loki log streams with matching trace_id and distinct instances."""
import argparse
import json
from pathlib import Path


def verify(response: dict, trace_id: str):
    if response.get('status') != 'success':
        raise ValueError('Loki API did not return success')
    streams = response.get('data', {}).get('result', [])
    found = {}
    for stream in streams:
        instance = stream.get('stream', {}).get('instance')
        if instance not in ('gateway-zone-a1', 'metadata-zone-a1'):
            continue
        for _, raw in stream.get('values', []):
            event = json.loads(raw)
            if event.get('trace_id') == trace_id:
                found[instance] = event
    if set(found) != {'gateway-zone-a1', 'metadata-zone-a1'}:
        raise ValueError('Loki missing matching Gateway and Metadata logs')
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('response', type=Path)
    parser.add_argument('trace_id')
    args = parser.parse_args()
    events = verify(json.loads(args.response.read_text()), args.trace_id)
    print('PASS: Loki correlated', ', '.join(sorted(events)), 'by trace_id')

if __name__ == '__main__':
    main()
