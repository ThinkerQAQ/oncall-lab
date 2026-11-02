#!/usr/bin/env python3
"""Validate real Grafana tiered firing/recovery emails received by local Mailpit.

This tool never sends emails or contacts external SMTP services. It only reads
messages that Grafana has already delivered to the local capture server.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import time
from urllib.request import urlopen

EXPECTED_RECIPIENT = "oncall@example.test"
LEVELS = {"P1": "CRITICAL", "P2": "WARNING"}
TITLE_PATTERN = re.compile(r"^\[(FIRING|RESOLVED)\]\[(P1|P2)\]\[(CRITICAL|WARNING)\] ")


def verify(data, require_recovery=True, since=None, required_priorities=None):
    messages = data.get("messages", [])
    if not isinstance(messages, list):
        raise ValueError("Mailpit response has no message list")
    requested = set(LEVELS if required_priorities is None else required_priorities)
    if not requested or not requested.issubset(LEVELS):
        raise ValueError("invalid requested synthetic priority set")

    observed = {}
    for msg in messages:
        if since is not None:
            try:
                stamp = datetime.fromisoformat(msg.get("Created", "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if stamp < since:
                continue

        subject = msg.get("Subject", "")
        tier = TITLE_PATTERN.match(subject)
        if not tier or "Synthetic Zone A Kitex RPC" not in subject:
            continue
        state, priority, severity = tier.groups()
        if priority not in requested:
            continue
        if severity != LEVELS[priority]:
            raise ValueError(f"invalid priority/severity pair: {priority}/{severity}")

        recipients = {
            row.get("Address")
            for row in msg.get("To", []) if isinstance(row, dict)
        }
        if EXPECTED_RECIPIENT not in recipients:
            raise ValueError(f"{priority} alert has an unexpected recipient")

        key = (priority, state.lower())
        observed[key] = msg

    states = {"firing", "resolved"} if require_recovery else {"firing"}
    missing = {(priority, state) for priority in requested for state in states} - set(observed)
    if missing:
        raise ValueError(f"missing real tiered notification: {sorted(missing)}")
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:28025")
    parser.add_argument("--timeout", type=int, default=0)
    parser.add_argument("--firing-only", action="store_true")
    parser.add_argument("--priorities", nargs="+", choices=list(LEVELS), default=list(LEVELS))
    parser.add_argument("--save", type=Path)
    parser.add_argument("--since", help="ISO-8601 start timestamp; ignores earlier mail")
    args = parser.parse_args()
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00")) if args.since else None
    if since is not None and since.tzinfo is None:
        parser.error("--since must include an explicit timezone offset")

    deadline = time.monotonic() + args.timeout
    while True:
        try:
            with urlopen(args.url.rstrip("/") + "/api/v1/messages", timeout=7) as resp:
                data = json.load(resp)
            seen = verify(data, require_recovery=not args.firing_only,
                          since=since, required_priorities=args.priorities)
            if args.save:
                args.save.parent.mkdir(parents=True, exist_ok=True)
                args.save.write_text(json.dumps({
                    "total_messages": data.get("total"),
                    "delivered": {
                        f"{priority}_{state}": {
                            "id": msg.get("ID"), "subject": msg.get("Subject"),
                            "timestamp": msg.get("Created")
                        } for (priority, state), msg in sorted(seen.items())
                    },
                    "note": "Real SMTP delivery to local Mailpit, synthetic alerts only",
                }, indent=2) + "\n")
            for (priority, state), msg in sorted(seen.items()):
                print(f"PASS {priority} {state.upper()}: {msg.get('Subject')}")
            return
        except (ValueError, OSError) as exc:
            if time.monotonic() >= deadline:
                parser.error(str(exc))
            time.sleep(3)


if __name__ == "__main__":
    main()
