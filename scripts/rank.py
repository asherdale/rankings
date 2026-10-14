#!/usr/bin/env python3
import argparse
import base64
import glob
import html
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

CATEGORIES = ("speed", "mobile", "accessibility", "seo", "agent_readiness", "clarity", "design", "copy")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36 RateMyHomepage/1.0 (+https://ratemyhomepage.pages.dev)"
)
BLOCK_MARKERS = (
    "access denied",
    "just a moment",
    "attention required",
    "verify you are human",
    "are you a robot",
    "request blocked",
    "pardon our interruption",
    "captcha",
)
DEFAULT_RUBRIC = {
    "weights": {c: 1 for c in CATEGORIES},
    "grades": [[95, "A+", "Exceptional"], [85, "A", "Excellent"], [70, "B", "Good"],
               [55, "C", "Average"], [40, "D", "Weak"], [0, "F", "Poor"]],
}
TONES = {"A+": "#059669", "A": "#16a34a", "B": "#65a30d", "C": "#ca8a04", "D": "#ea580c", "F": "#dc2626"}
DOMAIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


def fail(message):
    sys.exit(f"rank.py: {message}")


def resolve(domain):
    for url in (f"https://{domain}", f"https://www.{domain}"):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=20) as resp:
                return resp.geturl()
        except urllib.error.HTTPError as exc:
            return exc.geturl() or url
        except Exception:
            continue
    return f"https://{domain}"


LIGHTHOUSE = "lighthouse@13.5.0"
PSI = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def find_chrome():
    if os.environ.get("CHROME_PATH"):
        return os.environ["CHROME_PATH"]
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), "~/.cache/ms-playwright", "~/Library/Caches/ms-playwright", "/ms-playwright"]
    names = ("chrome-headless-shell", "headless_shell", "chrome", "Chromium.app/Contents/MacOS/Chromium")
    for root in filter(None, roots):
        for name in names:
            hits = sorted(glob.glob(os.path.join(os.path.expanduser(root), "chromium*", "*", name)))
            if hits:
                return hits[-1]
    return None


def lighthouse(url, preset, chrome):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "report.json")
        command = ["lighthouse"] if shutil.which("lighthouse") else ["npx", "-y", LIGHTHOUSE]
        command += [
            url, "--quiet", "--output=json", f"--output-path={path}",
            "--only-categories=performance,accessibility,seo", "--max-wait-for-load=30000",
            "--chrome-flags=--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage",
        ]
        if preset == "desktop":
            command.append("--preset=desktop")
        env = dict(os.environ, CHROME_PATH=chrome) if chrome else dict(os.environ)
        proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=150)
        if not os.path.exists(path):
            raise RuntimeError((proc.stderr or proc.stdout).strip()[-200:] or "Lighthouse produced no report")
        report = json.load(open(path))
    return parse(report, preset)


def pagespeed(url, preset):
    query = [("url", url), ("strategy", preset), ("key", os.environ["PSI_API_KEY"])]
    query += [("category", c) for c in ("PERFORMANCE", "ACCESSIBILITY", "SEO")]
    for attempt in range(5):
        try:
            with urllib.request.urlopen(f"{PSI}?{urllib.parse.urlencode(query)}", timeout=120) as resp:
                return parse(json.load(resp)["lighthouseResult"], preset)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 4:
                raise RuntimeError(f"PageSpeed HTTP {exc.code}")
            time.sleep(random.uniform(10, 30))


def parse(report, preset):
    if report.get("runtimeError", {}).get("code"):
        raise RuntimeError(report["runtimeError"].get("message", report["runtimeError"]["code"])[:200])
    if report.get("audits", {}).get("http-status-code", {}).get("score") == 0:
        raise RuntimeError("the page returned an error status")
    scores = {c: report["categories"].get(c, {}).get("score") for c in ("performance", "accessibility", "seo")}
    if any(score is None for score in scores.values()):
        raise RuntimeError("some categories could not be scored")
    shots = {"final": report["audits"].get("final-screenshot", {}).get("details", {}).get("data")}
    if preset == "desktop":
        shots["full"] = (report.get("fullPageScreenshot") or {}).get("screenshot", {}).get("data")
    return {c: round(s * 100) for c, s in scores.items()}, shots


def measure(urls, preset, chrome, install):
    if install:
        install.wait(timeout=180)
    attempts = [(lighthouse, (urls[0], preset, chrome))]
    if os.environ.get("PSI_API_KEY"):
        attempts += [(pagespeed, (url, preset)) for url in urls[:2]]
    last = None
    for run, run_args in attempts:
        try:
            return run(*run_args)
        except Exception as exc:
            last = exc
    raise last


def install_lighthouse():
    if shutil.which("lighthouse"):
        return None
    return subprocess.Popen(["npm", "install", "-g", "--silent", LIGHTHOUSE],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def browse_page(url, out):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        return browse(p, url, out)


CONSENT = re.compile(r"^\s*(accept all( cookies)?|accept( cookies)?|allow all( cookies)?|i agree|agree( and continue)?|got it|ok(ay)?)\s*$", re.I)


def dismiss_consent(page):
    for frame in page.frames:
        try:
            button = frame.get_by_role("button", name=CONSENT)
            if button.count():
                button.first.click(timeout=2000)
                page.wait_for_timeout(1500)
                return
        except Exception:
            continue


def data_url(path):
    mime = {".png": "image/png", ".webp": "image/webp"}.get(path.suffix, "image/jpeg")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def write_data_url(value, path):
    if not value:
        return None
    header, _, payload = value.partition(",")
    target = path.with_suffix(".webp" if "webp" in header else ".png" if "png" in header else ".jpg")
    target.write_bytes(base64.b64decode(payload))
    return target


def browse(p, url, out):
    browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    try:
        page = browser.new_context(viewport={"width": 1440, "height": 900}, user_agent=USER_AGENT, locale="en-US").new_page()
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)
        dismiss_consent(page)
        info = {
            "status": resp.status if resp else None,
            "title": page.title(),
            "description": page.evaluate("() => document.querySelector('meta[name=description]')?.content || ''"),
            "headings": page.evaluate("() => [...document.querySelectorAll('h1')].map(h => h.innerText.trim()).filter(Boolean).slice(0, 5)"),
            "text": page.evaluate("() => document.body ? document.body.innerText : ''"),
        }
        text = (info["title"] + " " + info["text"][:2000]).lower()
        if (info["status"] or 0) >= 400 or (len(info["text"]) < 3000 and any(m in text for m in BLOCK_MARKERS)):
            return {**info, "blocked": True}
        page.screenshot(path=str(out / "desktop.jpg"), type="jpeg", quality=80)
        height = min(page.evaluate("() => document.documentElement.scrollHeight"), 4000)
        page.screenshot(path=str(out / "full.jpg"), type="jpeg", quality=60, full_page=True,
                        clip={"x": 0, "y": 0, "width": 1440, "height": max(height, 900)})
        small = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=0.5,
                                    user_agent=USER_AGENT, locale="en-US").new_page()
        small.goto(page.url, wait_until="domcontentloaded", timeout=45000)
        small.wait_for_timeout(3000)
        dismiss_consent(small)
        small.screenshot(path=str(out / "thumb.jpg"), type="jpeg", quality=80)
        mobile = browser.new_context(**{**p.devices["iPhone 13"], "user_agent": USER_AGENT}, locale="en-US").new_page()
        mobile.goto(page.url, wait_until="domcontentloaded", timeout=45000)
        mobile.wait_for_timeout(4000)
        dismiss_consent(mobile)
        mobile.screenshot(path=str(out / "mobile.jpg"), type="jpeg", quality=80)
        return {**info, "blocked": False}
    finally:
        browser.close()


SHEET = """<!doctype html><html><head><meta charset="utf-8"><style>
* {{ margin: 0; box-sizing: border-box; }}
body {{ width: 2000px; background: #f2f2f2; font: 600 22px system-ui, sans-serif; color: #555; padding: 24px; }}
.row {{ display: flex; gap: 24px; align-items: flex-start; }}
.col {{ display: flex; flex-direction: column; gap: 10px; }}
img {{ display: block; border: 1px solid #ddd; background: #fff; }}
</style></head><body><div class="row">
<div class="col"><div>Desktop, first screen</div><img src="{desktop}" style="width: 1100px"></div>
<div class="col"><div>Phone</div><img src="{mobile}" style="width: 330px"></div>
<div class="col"><div>Full page</div><img src="{full}" style="width: 470px"></div>
</div></body></html>"""


def render(p, page_html, path, width, height=None, full_page=False):
    browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    try:
        page = browser.new_page(viewport={"width": width, "height": height or 800})
        page.set_content(page_html, wait_until="networkidle", timeout=30000)
        page.screenshot(path=str(path), type="jpeg", quality=85, full_page=full_page)
    finally:
        browser.close()


def collect(args):
    from playwright.sync_api import sync_playwright

    out = Path(args.out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    domain = args.domain
    url = resolve(domain)
    urls = list(dict.fromkeys([url, f"https://{domain}", f"https://www.{domain}"]))
    result = {"domain": domain, "url": url, "started_at": time.time()}
    install = install_lighthouse()
    chrome = find_chrome()
    if not chrome:
        with sync_playwright() as p:
            if os.path.exists(p.chromium.executable_path):
                chrome = p.chromium.executable_path
    with ThreadPoolExecutor(max_workers=3) as pool:
        mobile = pool.submit(measure, urls, "mobile", chrome, install)
        desktop = pool.submit(measure, urls, "desktop", chrome, install)
        browsed = pool.submit(browse_page, url, out)
        try:
            page = browsed.result()
        except Exception as exc:
            page = {"blocked": True, "error": str(exc).splitlines()[0][:200]}
        try:
            (mobile_scores, mobile_shots), (desktop_scores, desktop_shots) = mobile.result(), desktop.result()
        except Exception as exc:
            result.update(skip=True, reason=f"Lighthouse couldn't load the site: {str(exc)[:200]}")
            (out / "collect.json").write_text(json.dumps(result, indent=2))
            print(json.dumps({k: result[k] for k in ("domain", "skip", "reason")}, indent=2))
            return
    with sync_playwright() as p:
        if page["blocked"]:
            page.update(title="", description="", headings=[], text="")
            for name in ("desktop.jpg", "full.jpg", "thumb.jpg", "mobile.jpg"):
                (out / name).unlink(missing_ok=True)
            write_data_url(desktop_shots.get("final"), out / "desktop")
            write_data_url(mobile_shots.get("final"), out / "mobile")
            write_data_url(desktop_shots.get("full"), out / "full")
            if (out / "desktop.jpg").exists():
                shutil.copy(out / "desktop.jpg", out / "thumb.jpg")
        shots = {name: next(out.glob(f"{name}.*"), None) for name in ("desktop", "mobile", "full")}
        shots["mobile"] = shots["mobile"] or shots["desktop"]
        shots["full"] = shots["full"] or shots["desktop"]
        if not shots["desktop"]:
            result.update(skip=True, reason="no screenshots were available")
            (out / "collect.json").write_text(json.dumps(result, indent=2))
            print(json.dumps({k: result[k] for k in ("domain", "skip", "reason")}, indent=2))
            return
        render(p, SHEET.format(**{k: data_url(v) for k, v in shots.items()}), out / "sheet.jpg", 2000, full_page=True)

    result.update(
        lighthouse={"mobile": mobile_scores, "desktop": desktop_scores},
        blocks_automated_browsers=page["blocked"],
        title=page.get("title") or "",
        description=page.get("description") or "",
        headings=page.get("headings") or [],
        text=(page.get("text") or "")[:1500],
    )
    (out / "collect.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k not in ("started_at", "url")}, indent=2))


CARD = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap">
<style>
* {{ box-sizing: border-box; margin: 0; }}
body {{ width: 1200px; height: 630px; background: #fff; font-family: Geist, Inter, system-ui, sans-serif; color: #0a0a0a; }}
.card {{ display: grid; grid-template-columns: 1fr 470px; height: 100%; }}
.left {{ padding: 60px 40px 52px 64px; display: flex; flex-direction: column; }}
.site {{ display: flex; align-items: center; gap: 14px; }}
.site img {{ width: 40px; height: 40px; border-radius: 9px; }}
.domain {{ font-size: 40px; font-weight: 600; letter-spacing: -0.03em; }}
.roast {{ margin-top: 26px; font-size: 30px; line-height: 1.3; font-weight: 500; letter-spacing: -0.01em; color: #262626; }}
.score {{ display: flex; align-items: center; gap: 22px; margin-top: auto; }}
.num {{ font-size: 132px; font-weight: 700; line-height: 0.85; letter-spacing: -0.05em; color: {tone}; }}
.grade {{ font-size: 48px; font-weight: 700; color: {tone}; background: {tint}; border-radius: 14px; padding: 4px 18px; }}
.brand {{ font-size: 18px; color: #737373; line-height: 1.4; }}
.right {{ padding: 52px 52px 52px 0; }}
.shot {{ width: 100%; height: 100%; border-radius: 16px; border: 1px solid #ebebeb; background: #fafafa left top / cover no-repeat url("{shot}"); }}
</style></head><body><div class="card">
<div class="left">
<div class="site"><img src="https://www.google.com/s2/favicons?domain={domain}&sz=128"><div class="domain">{domain}</div></div>
<div class="roast">“{roast}”</div>
<div class="score"><div class="num">{composite}</div><div><div class="grade">{letter}</div></div><div class="brand">ratemyhomepage.pages.dev<br>scored by AI agents on Omnara</div></div>
</div>
<div class="right"><div class="shot"></div></div>
</div></body></html>"""


def score(value, name):
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
        fail(f"{name} must be an integer from 0 to 100, got {value!r}")
    return value


def sentence(value, name, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\n" in value.strip():
        fail(f"{name} must be one sentence of at most {limit} characters")
    return value.strip()


def load_rubric():
    here = Path(__file__).resolve().parent
    for path in (here / "rubric.json", here.parent / "rubric.json"):
        if path.exists():
            return json.loads(path.read_text())
    return DEFAULT_RUBRIC


def finish(args):
    from playwright.sync_api import sync_playwright

    out = Path(args.out)
    collected = json.loads((out / "collect.json").read_text())
    if collected.get("domain") != args.domain or collected.get("skip"):
        fail(f"no usable collect.json for {args.domain}")
    try:
        review = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        fail(f"the review on stdin isn't valid JSON ({exc})")

    lh = collected["lighthouse"]
    scores = {
        "speed": score(lh["desktop"]["performance"], "speed"),
        "mobile": score(lh["mobile"]["performance"], "mobile"),
        "accessibility": score(lh["mobile"]["accessibility"], "accessibility"),
        "seo": score(lh["mobile"]["seo"], "seo"),
        "agent_readiness": score(review.get("ora_score"), "ora_score"),
        "clarity": score(review.get("clarity"), "clarity"),
        "design": score(review.get("design"), "design"),
        "copy": score(review.get("copy"), "copy"),
    }
    rubric = load_rubric()
    weights = rubric["weights"]
    composite = round(sum(scores[c] * weights[c] for c in CATEGORIES) / sum(weights[c] for c in CATEGORIES))
    letter = next(g[1] for g in rubric["grades"] if composite >= g[0])
    result = {
        "domain": args.domain,
        "status": "done",
        "audited_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "composite": composite,
        "roast": sentence(review.get("roast"), "roast"),
        "fix": sentence(review.get("fix"), "fix"),
        "scores": scores,
        "notes": {"agent_readiness": sentence(review["ora_summary"], "ora_summary", 300)} if review.get("ora_summary") else {},
        "model": sentence(review.get("model"), "model", 80),
        "blocks_automated_browsers": bool(collected.get("blocks_automated_browsers")),
        "minutes": max(1, round((time.time() - collected["started_at"]) / 60)),
    }

    tone = TONES[letter]
    thumb = next((out / n for n in ("thumb.jpg", "desktop.jpg") if (out / n).exists()), None)
    card = CARD.format(tone=tone, tint=tone + "22", shot=data_url(thumb) if thumb else "", domain=html.escape(args.domain),
                       roast=html.escape(result["roast"]), composite=composite, letter=letter)
    with sync_playwright() as p:
        render(p, card, out / "card.jpg", 1200, 630)

    bundle = out / f"{args.domain}.tar.gz"
    with tarfile.open(bundle, "w:gz") as tar:
        def add(name, data):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        add(f"results/{args.domain}.json", (json.dumps(result, indent=2) + "\n").encode())
        add(f"cards/{args.domain}.jpg", (out / "card.jpg").read_bytes())
        if thumb:
            add(f"shots/{args.domain}.jpg", thumb.read_bytes())
    print(json.dumps({"domain": args.domain, "composite": composite, "grade": letter, "bundle": str(bundle)}))


def main():
    parser = argparse.ArgumentParser(description="Rank one website for Rate My Homepage.")
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("collect", help="get Lighthouse scores, screenshots, and page text")
    two = sub.add_parser("finish", help="score the site from the review on stdin and bundle the result")
    for command in (one, two):
        command.add_argument("domain")
        command.add_argument("--out", default="/workspace/out")
    args = parser.parse_args()
    if not DOMAIN.match(args.domain):
        fail(f"bad domain {args.domain!r}")
    collect(args) if args.command == "collect" else finish(args)


if __name__ == "__main__":
    main()
