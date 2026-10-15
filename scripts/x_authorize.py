#!/usr/bin/env python3
import argparse
import base64
import hashlib
import hmac
import os
import secrets
import time
import urllib.parse
import urllib.request
from pathlib import Path

REQUEST = "https://api.x.com/oauth/request_token"
AUTHORIZE = "https://api.x.com/oauth/authorize"
ACCESS = "https://api.x.com/oauth/access_token"


def signed_post(url, extra, token_secret=""):
    quote = lambda value: urllib.parse.quote(value, safe="~")
    params = {
        "oauth_consumer_key": os.environ["X_API_KEY"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_version": "1.0",
        **extra,
    }
    base = "&".join(["POST", quote(url), quote("&".join(f"{quote(k)}={quote(v)}" for k, v in sorted(params.items())))])
    key = f"{quote(os.environ['X_API_SECRET'])}&{quote(token_secret)}"
    params["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    header = "OAuth " + ", ".join(f'{quote(k)}="{quote(v)}"' for k, v in sorted(params.items()))
    request = urllib.request.Request(url, data=b"", method="POST", headers={"Authorization": header})
    with urllib.request.urlopen(request, timeout=30) as resp:
        return dict(urllib.parse.parse_qsl(resp.read().decode()))


def main():
    parser = argparse.ArgumentParser(description="Let the app post as an X account, and save that account's access token.")
    parser.add_argument("--env-file", required=True, help="append X_ACCESS_TOKEN and X_ACCESS_SECRET to this file")
    args = parser.parse_args()

    request = signed_post(REQUEST, {"oauth_callback": "oob"})
    print("Open this link while logged in as the account that should post, and approve the app:")
    print(f"{AUTHORIZE}?oauth_token={request['oauth_token']}")
    pin = input("PIN: ").strip()
    access = signed_post(ACCESS, {"oauth_token": request["oauth_token"], "oauth_verifier": pin},
                         request["oauth_token_secret"])
    with Path(args.env_file).open("a") as env:
        env.write(f"\nX_ACCESS_TOKEN={access['oauth_token']}\nX_ACCESS_SECRET={access['oauth_token_secret']}\n")
    print(f"Saved the access token for @{access['screen_name']} to {args.env_file}.")


if __name__ == "__main__":
    main()
