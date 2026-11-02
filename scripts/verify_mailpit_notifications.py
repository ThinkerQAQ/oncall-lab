#!/usr/bin/env python3
"""Verify real Grafana alert email delivery to the isolated Mailpit inbox.

The API never sends email; Mailpit is a local SMTP sink. Running this command
requires that Grafana Alerting already performed the actual SMTP delivery.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from urllib.request import urlopen

EXPECTED_RECIPIENT = "oncall@example.test"
EXPECTED_ALERT = "Synthetic Zone A Kitex RPC timeout rate"


def verify(data, require_recovery=True, since=None):
    messages = data.get("messages", [])
    if not isinstance(messages, list):
        raise ValueError("Mailpit response has no message list")

    observed = {}
    for msg in messages:
        if since is not None:
            try:
                timestamp = datetime.fromisoformat(msg.get("Created", "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if timestamp < since:
                continue
        subject = msg.get("Subject", "")
        if EXPECTED_ALERT not in subject:
            continue
        recipients = {
            r.get("Address")
            for r in msg.get("To", [])
            if isinstance(r, dict)
        }
        if EXPECTED_RECIPIENT not in recipients:
            raise ValueError("synthetic on-call alert has unexpected recipient")
        if subject.startswith("[FIRING:"):
            observed["firing"] = msg
        elif subject.startswith("[RESOLVED]"):
            observed["resolved"] = msg
    required = {"firing", "resolved"} if require_recovery else {"firing"}
    if not required.issubset(observed):
        raise ValueError(f"missing actual delivered email: {required - set(observed)}")
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:28025")
    parser.add_argument("--timeout", type=int, default=0)
    parser.add_argument("--firing-only", action="store_true")
    parser.add_argument("--save", type=Path)
    parser.add_argument("--since", help="UTC ISO-8601 experiment start; ignore older messages")
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00")) if args.since else None
    if since is not None and since.tzinfo is None:
        parser.error("--since requires an explicit timezone offset")

    while True:
        try:
            with urlopen(args.url.rstrip("/") + "/api/v1/messages", timeout=7) as response:
                data = json.load(response)
            observed = verify(data, require_recovery=not args.firing_only, since=since)
            if args.save:
                args.save.parent.mkdir(parents=True, exist_ok=True)
                args.save.write_text(json.dumps({
                    "total_messages": data.get("total"),
                    "delivered": {
                        kind: {"id": message.get("ID"),
                               "subject": message.get("Subject"),
                               "timestamp": message.get("Created")}
                        for kind, message in observed.items()
                    },
                    "note": "Actual Mailpit SMTP sink, synthetic lab recipient only.",
                }, indent=2) + "\n")
            for kind, message in sorted(observed.items()):
                print(f"PASS {kind.upper()}: {message.get('Subject')}")
            return
        except (ValueError, OSError) as exc:
            if time.monotonic() >= deadline:
                parser.error(str(exc))
            time.sleep(3)


if __name__ == "__main__":
    main()
