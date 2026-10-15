#!/usr/bin/env python3
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPLOAD = "https://api.x.com/2/media/upload"
POST = "https://api.x.com/2/tweets"
JUDGES = (("claude", "Claude"), ("gpt", "GPT"), ("gemini", "Gemini"), ("muse", "Muse"))


def oauth_header(method, url):
    quote = lambda value: urllib.parse.quote(value, safe="~")
    params = {
        "oauth_consumer_key": os.environ["X_API_KEY"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": os.environ["X_ACCESS_TOKEN"],
        "oauth_version": "1.0",
    }
    base = "&".join([method, quote(url), quote("&".join(f"{quote(k)}={quote(v)}" for k, v in sorted(params.items())))])
    key = f"{quote(os.environ['X_API_SECRET'])}&{quote(os.environ['X_ACCESS_SECRET'])}"
    params["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{quote(k)}="{quote(v)}"' for k, v in sorted(params.items()))


def call(url, body, content_type):
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Authorization": oauth_header("POST", url), "Content-Type": content_type})
    with urllib.request.urlopen(request, timeout=60) as resp:
        return json.load(resp)


def upload(image):
    boundary = uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="media_category"\r\n\r\ntweet_image\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="media"; filename="card.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + image.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    return call(UPLOAD, body, f"multipart/form-data; boundary={boundary}")["data"]["id"]


def text_for(result, site_url):
    judges = " · ".join(f"{name} {result['judges'][key]['score']}" for key, name in JUDGES)
    return f"{result['score']:.1f}/10 · {judges}\nall four roasts: {site_url}/{result['domain']}/"


def main():
    site_url = json.loads((ROOT / "site" / "config.json").read_text())["site_url"].rstrip("/")
    sent = ROOT / "replies" / "sent.txt"
    for request in sorted((ROOT / "replies").glob("*.json")):
        job = json.loads(request.read_text())
        result = json.loads((ROOT / "results" / f"{job['domain']}.json").read_text())
        if result.get("status") != "done":
            continue
        try:
            media = upload(ROOT / "cards" / f"{job['domain']}.jpg")
            body = {"text": text_for(result, site_url), "reply": {"in_reply_to_tweet_id": job["reply_id"]}, "media": {"media_ids": [media]}}
            call(POST, json.dumps(body).encode(), "application/json")
            print(f"replied to {job['reply_id']} with {job['domain']}")
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                print(f"will retry {job['reply_id']}: HTTP {exc.code}")
                continue
            print(f"gave up on {job['reply_id']}: HTTP {exc.code} {exc.read()[:200]!r}")
        request.unlink()
        with sent.open("a") as log:
            log.write(job["reply_id"] + "\n")


if __name__ == "__main__":
    main()
