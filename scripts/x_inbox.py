#!/usr/bin/env python3
import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from enqueue import normalize

ROOT = Path(__file__).resolve().parent.parent
STATE = Path("/workspace/x_inbox.json")
SEARCH = "https://api.x.com/2/tweets/search/recent"
IGNORED_HOSTS = ("x.com", "twitter.com", "t.co", "ratemyhomepage.pages.dev")
TOKEN = re.compile(r"(?<![@\w])(?:https?://)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?", re.I)


def launch_post():
    config = json.loads((ROOT / "site" / "config.json").read_text())
    match = re.search(r"/status/(\d+)", config.get("x_post_url", ""))
    if not match or not config.get("x_handle"):
        raise SystemExit("x_inbox.py: set x_post_url and x_handle in site/config.json")
    return match.group(1), config["x_handle"].lower()


def search(post, since):
    params = {
        "query": f"conversation_id:{post} is:reply -is:retweet",
        "max_results": "100",
        "tweet.fields": "author_id,entities",
        "expansions": "author_id",
        "user.fields": "username",
    }
    if since:
        params["since_id"] = since
    replies, users = [], {}
    for _ in range(10):
        request = urllib.request.Request(f"{SEARCH}?{urllib.parse.urlencode(params)}",
                                         headers={"Authorization": f"Bearer {os.environ['X_BEARER_TOKEN']}"})
        with urllib.request.urlopen(request, timeout=30) as resp:
            page = json.load(resp)
        replies += page.get("data", [])
        users.update({u["id"]: u["username"] for u in page.get("includes", {}).get("users", [])})
        if "next_token" not in page.get("meta", {}):
            break
        params["next_token"] = page["meta"]["next_token"]
    return replies, users


def domain_of(reply):
    candidates = [u.get("expanded_url", "") for u in reply.get("entities", {}).get("urls", [])]
    candidates += TOKEN.findall(reply.get("text", ""))
    for candidate in candidates:
        domain = normalize(candidate)
        if domain and not domain.endswith(IGNORED_HOSTS):
            return domain
    return None


def main():
    parser = argparse.ArgumentParser(description="Print new replies to the launch post that name a website.")
    parser.add_argument("--since", help="only replies newer than this post ID")
    args = parser.parse_args()

    post, handle = launch_post()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    replies, users = search(post, args.since or state.get("newest_id"))
    sent_log = ROOT / "replies" / "sent.txt"
    sent = set(sent_log.read_text().split()) if sent_log.exists() else set()
    pending = state.get("pending", [])
    known = sent | {request["reply_id"] for request in pending}
    asked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    found = []
    for reply in sorted(replies, key=lambda r: int(r["id"])):
        author = users.get(reply["author_id"], "")
        domain = domain_of(reply)
        mentioned = {m.get("username", "").lower() for m in reply.get("entities", {}).get("mentions", [])}
        if not domain or handle not in mentioned or author.lower() == handle or reply["id"] in known:
            continue
        result = ROOT / "results" / f"{domain}.json"
        ranked = result.exists() and json.loads(result.read_text()).get("status") == "done"
        found.append({"reply_id": reply["id"], "author": author, "domain": domain, "ranked": ranked})
        pending.append({"reply_id": reply["id"], "domain": domain, "asked_at": asked_at})
    newest = max([int(r["id"]) for r in replies] + [int(state.get("newest_id") or 0)])
    STATE.write_text(json.dumps({"newest_id": str(newest) if newest else None, "pending": pending}))
    print(json.dumps({"replies": found, "newest_id": str(newest) if newest else None}, indent=2))


if __name__ == "__main__":
    main()
