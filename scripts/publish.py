#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
CATEGORIES = ("speed", "mobile", "accessibility", "seo", "agent_readiness", "clarity", "design", "copy")
KEYS = {"domain", "status", "audited_at", "composite", "roast", "fix", "scores", "notes", "model",
        "blocks_automated_browsers", "minutes"}
JPEG = b"\xff\xd8\xff"


def is_score(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100


def is_text(value, limit):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit and "\n" not in value.strip()


def check_result(data, domain):
    if set(data) - KEYS or data.get("domain") != domain or data.get("status") != "done":
        return "unexpected fields, domain, or status"
    if not is_score(data.get("composite")) or set(data.get("scores", {})) != set(CATEGORIES):
        return "missing scores"
    if not all(is_score(data["scores"][c]) for c in CATEGORIES):
        return "scores must be integers from 0 to 100"
    texts = [(data.get("roast"), 200), (data.get("fix"), 200), (data.get("model"), 80)]
    texts += [(v, 300) for v in data.get("notes", {}).values()]
    if set(data.get("notes", {})) - {"agent_readiness"} or not all(is_text(v, n) for v, n in texts):
        return "text fields must be single sentences within length limits"
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

    git("add", "-A", "--", "results", "cards", "shots")
    pushed = False
    if git("diff", "--cached", "--quiet", check=False).returncode:
        git("commit", "-m", f"Rank {len(published)} site{'s' if len(published) != 1 else ''}" if published else "Update queue")
        if git("push", check=False).returncode:
            git("pull", "--rebase")
            git("push")
        pushed = True
    print(json.dumps({"published": published, "problems": problems, "pushed": pushed}, indent=2))
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
