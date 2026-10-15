#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from x_inbox import STATE as X_STATE

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
JUDGES = {"claude", "gpt", "gemini", "muse"}
MEASUREMENTS = ("mobile_speed", "desktop_speed", "accessibility", "seo", "agent_readiness")
KEYS = {"domain", "status", "audited_at", "score", "judges", *MEASUREMENTS, "agent_readiness_summary",
        "blocks_automated_browsers", "minutes"}
JPEG = b"\xff\xd8\xff"
STALE = timedelta(minutes=20)
UNANSWERED = timedelta(hours=1)


def older_than(stamp, limit):
    if not stamp:
        return True
    return datetime.now(timezone.utc) - datetime.fromisoformat(stamp.replace("Z", "+00:00")) > limit


def is_int(value, low, high):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def is_text(value, limit):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit and "\n" not in value.strip()


def check_result(data, domain):
    if set(data) - KEYS or data.get("domain") != domain or data.get("status") != "done":
        return "unexpected fields, domain, or status"
    judges = data.get("judges")
    if not isinstance(judges, dict) or set(judges) != JUDGES:
        return "judges must be claude, gpt, gemini, and muse"
    for judge in judges.values():
        if set(judge) != {"model", "score", "roast"} or not is_int(judge["score"], 1, 10):
            return "each judge needs a model, a score from 1 to 10, and a roast"
        if not is_text(judge["model"], 80) or not is_text(judge["roast"], 200):
            return "judge text fields must be single sentences within length limits"
    if data.get("score") != round(sum(j["score"] for j in judges.values()) / len(judges), 1):
        return "score must be the judges' average"
    if not all(key in data and (data[key] is None or is_int(data[key], 0, 100)) for key in MEASUREMENTS):
        return "measurements must be integers from 0 to 100, or null"
    if "agent_readiness_summary" in data and not is_text(data["agent_readiness_summary"], 300):
        return "agent_readiness_summary must be one sentence"
    if not isinstance(data.get("minutes"), int) or not isinstance(data.get("blocks_automated_browsers"), bool):
        return "bad minutes or blocks_automated_browsers"
    return None


def unpack(bundle):
    domain = bundle.name.removesuffix(".tar.gz")
    if not DOMAIN.match(domain):
        return None, "bad file name"
    allowed = {f"results/{domain}.json", f"cards/{domain}.jpg", f"shots/{domain}.jpg"}
    files = {}
    with tarfile.open(bundle, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or member.name not in allowed or member.size > 2_000_000:
                return None, f"unexpected entry {member.name!r}"
            files[member.name] = tar.extractfile(member).read()
    if f"results/{domain}.json" not in files or f"cards/{domain}.jpg" not in files:
        return None, "missing the result or the card"
    if not all(data.startswith(JPEG) for name, data in files.items() if name.endswith(".jpg")):
        return None, "images must be JPEGs"
    try:
        error = check_result(json.loads(files[f"results/{domain}.json"]), domain)
    except json.JSONDecodeError:
        error = "unreadable result"
    return (None, error) if error else (files, None)


def queue_replies(skipped):
    state = json.loads(X_STATE.read_text()) if X_STATE.exists() else {}
    sent_log = ROOT / "replies" / "sent.txt"
    sent = set(sent_log.read_text().split()) if sent_log.exists() else set()
    replies, waiting = [], []
    for request in state.get("pending", []):
        domain, post = request["domain"], request["reply_id"]
        path = ROOT / "results" / f"{domain}.json"
        if post in sent:
            continue
        if path.exists() and json.loads(path.read_text()).get("status") == "done":
            (ROOT / "replies").mkdir(exist_ok=True)
            (ROOT / "replies" / f"{post}.json").write_text(json.dumps({"domain": domain, "reply_id": post}) + "\n")
            replies.append(f"{domain}:{post}")
        elif domain not in skipped and not older_than(request.get("asked_at"), UNANSWERED):
            waiting.append(request)
    if state:
        X_STATE.write_text(json.dumps({**state, "pending": waiting}))
    return replies


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, check=check, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description="Publish finished bundles from the inbox and push them.")
    parser.add_argument("--inbox", default="/workspace/inbox")
    parser.add_argument("--skip", nargs="*", default=[], help="domains that were skipped; their placeholders are removed")
    args = parser.parse_args()

    inbox = Path(args.inbox)
    rejected = inbox.parent / "rejected"
    published, problems = [], []
    for bundle in sorted(inbox.glob("*.tar.gz")) if inbox.exists() else []:
        try:
            files, error = unpack(bundle)
        except (tarfile.TarError, OSError) as exc:
            files, error = None, f"unreadable bundle ({exc})"
        if error:
            rejected.mkdir(exist_ok=True)
            shutil.move(str(bundle), rejected / bundle.name)
            problems.append(f"{bundle.name}: {error}")
            continue
        for name, data in files.items():
            (ROOT / name).parent.mkdir(exist_ok=True)
            (ROOT / name).write_bytes(data)
        bundle.unlink()
        published.append(bundle.name.removesuffix(".tar.gz"))
    for domain in args.skip:
        path = ROOT / "results" / f"{domain}.json"
        if DOMAIN.match(domain) and path.exists() and json.loads(path.read_text()).get("status") == "scoring":
            path.unlink()
    for path in (ROOT / "results").glob("*.json"):
        placeholder = json.loads(path.read_text())
        if placeholder.get("status") == "scoring" and older_than(placeholder.get("queued_at"), STALE):
            path.unlink()

    replies = queue_replies(set(args.skip))

    git("add", "-A", "--", "results", "cards", "shots", "replies")
    pushed = False
    if git("diff", "--cached", "--quiet", check=False).returncode:
        git("commit", "-m", f"Rank {len(published)} site{'s' if len(published) != 1 else ''}" if published else "Update queue")
        for _ in range(5):
            if not git("push", check=False).returncode:
                pushed = True
                break
            git("pull", "--rebase")
    print(json.dumps({"published": published, "replies": replies, "problems": problems, "pushed": pushed}, indent=2))
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
