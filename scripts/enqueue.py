#!/usr/bin/env python3
import argparse
import ipaddress
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
INTERNAL = (".local", ".internal", ".localhost", ".lan", ".home", ".corp", ".test", ".invalid", ".example")


def normalize(raw):
    host = re.sub(r"^[a-z]+://", "", raw.strip().lower()).split("/")[0].split(":")[0]
    host = host.removeprefix("www.").strip(".")
    if not DOMAIN.match(host) or host.endswith(INTERNAL) or host == "localhost":
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        return host


def main():
    parser = argparse.ArgumentParser(description="Queue domains: write a 'scoring' placeholder for each one.")
    parser.add_argument("domains", nargs="*", help="domains, or a file of them with --file")
    parser.add_argument("--file", help="a file with one domain per line")
    parser.add_argument("--rerun", action="store_true", help="rank sites again even if they're done")
    args = parser.parse_args()

    raw = list(args.domains)
    if args.file:
        raw += [line.split("#")[0] for line in (ROOT / args.file).read_text().splitlines()]
    queued, done, rejected = [], [], []
    for item in dict.fromkeys(token for entry in raw for token in re.split(r"[\s,]+", entry) if token):
        domain = normalize(item)
        if not domain:
            rejected.append(item)
            continue
        path = ROOT / "results" / f"{domain}.json"
        existing = json.loads(path.read_text()) if path.exists() else {}
        if existing.get("status") == "done" and not args.rerun:
            done.append(domain)
            continue
        if domain not in queued:
            queued.append(domain)
            if existing.get("status") != "done":
                queued_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                path.write_text(json.dumps({"domain": domain, "status": "scoring", "queued_at": queued_at}, indent=2) + "\n")
    print(json.dumps({"queued": queued, "already_ranked": done, "rejected": rejected}, indent=2))


if __name__ == "__main__":
    main()
