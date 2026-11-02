#!/usr/bin/env python3
"""Verify that Grafana really wrote firing and recovery transitions to Loki."""
import argparse
import json
from pathlib import Path


def verify(data):
    if data.get('status') != 'success':
        raise ValueError('Loki query did not succeed')
    transitions = []
    for stream in data.get('data', {}).get('result', []):
        if stream.get('stream', {}).get('from') != 'state-history':
            continue
        for _, raw in stream.get('values', []):
            event = json.loads(raw)
            if event.get('ruleUID') == 'oncall_zone_a_timeout':
                transitions.append((event.get('previous'), event.get('current')))
    if ('Normal', 'Alerting') not in transitions:
        raise ValueError('missing real Normal -> Alerting transition')
    if ('Alerting', 'Normal') not in transitions:
        raise ValueError('missing real Alerting -> Normal transition')
    return transitions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('loki_json', type=Path)
    args = parser.parse_args()
    try:
        transitions = verify(json.loads(args.loki_json.read_text()))
    except (ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    print('PASS: Grafana alert state history includes', transitions)


if __name__ == '__main__':
    main()
