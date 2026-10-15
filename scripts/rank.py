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

DEADLINE = time.monotonic() + 300
JUDGES = {"claude": "Claude", "gpt": "GPT", "gemini": "Gemini", "muse": "Muse"}
GRADES = ((9.5, "A+"), (8.5, "A"), (7, "B"), (5.5, "C"), (4, "D"), (0, "F"))
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
        proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=remaining(150))
        if not os.path.exists(path):
            raise RuntimeError((proc.stderr or proc.stdout).strip()[-200:] or "Lighthouse produced no report")
        report = json.load(open(path))
    return parse(report, preset)


def pagespeed(url, preset):
    query = [("url", url), ("strategy", preset), ("key", os.environ["PSI_API_KEY"])]
    query += [("category", c) for c in ("PERFORMANCE", "ACCESSIBILITY", "SEO")]
    for attempt in range(5):
        try:
            with urllib.request.urlopen(f"{PSI}?{urllib.parse.urlencode(query)}", timeout=remaining(120)) as resp:
                return parse(json.load(resp)["lighthouseResult"], preset)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 4 or remaining(30) < 30:
                raise RuntimeError(f"PageSpeed HTTP {exc.code}")
            time.sleep(random.uniform(10, 30))


def parse(report, preset):
    if report.get("runtimeError", {}).get("code"):
        raise RuntimeError(report["runtimeError"].get("message", report["runtimeError"]["code"])[:200])
    if report.get("audits", {}).get("http-status-code", {}).get("score") == 0:
        raise RuntimeError("the page returned an error status")
    scores = {c: report["categories"].get(c, {}).get("score") for c in ("performance", "accessibility", "seo")}
    if all(score is None for score in scores.values()):
        raise RuntimeError("no categories could be scored")
    shots = {"final": report["audits"].get("final-screenshot", {}).get("details", {}).get("data")}
    if preset == "desktop":
        shots["full"] = (report.get("fullPageScreenshot") or {}).get("screenshot", {}).get("data")
    return {c: None if s is None else round(s * 100) for c, s in scores.items()}, shots


def measure(urls, preset, chrome, install):
    if install:
        install.wait(timeout=remaining(180))
    attempts = [(lighthouse, (urls[0], preset, chrome))]
    if os.environ.get("PSI_API_KEY"):
        attempts += [(pagespeed, (url, preset)) for url in urls[:2]]
    last = RuntimeError("timed out")
    for run, run_args in attempts:
        if remaining(1) < 1:
            break
        try:
            return run(*run_args)
        except Exception as exc:
            last = exc
    raise last


def remaining(cap):
    return max(0, min(cap, DEADLINE - time.monotonic()))


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


def measure_site(args):
    out = Path(args.out)
    domain = args.domain
    url = resolve(domain)
    urls = list(dict.fromkeys([url, f"https://{domain}", f"https://www.{domain}"]))
    install = install_lighthouse()
    chrome = find_chrome()
    if not chrome:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            if os.path.exists(p.chromium.executable_path):
                chrome = p.chromium.executable_path
    report = {"scores": {}, "shots": {}, "failures": []}
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = {preset: pool.submit(measure, urls, preset, chrome, install) for preset in ("mobile", "desktop")}
        for preset, future in runs.items():
            try:
                report["scores"][preset], report["shots"][preset] = future.result()
            except Exception as exc:
                report["scores"][preset], report["shots"][preset] = {}, {}
                report["failures"].append(str(exc)[:200])
    (out / "lighthouse.tmp").write_text(json.dumps(report))
    (out / "lighthouse.tmp").replace(out / "lighthouse.json")


def lighthouse_report(out, timeout):
    path = out / "lighthouse.json"
    end = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < end:
        time.sleep(1)
    if not path.exists():
        return {"scores": {"mobile": {}, "desktop": {}}, "shots": {"mobile": {}, "desktop": {}}, "failures": ["Lighthouse timed out"]}
    return json.loads(path.read_text())


def shoot(args):
    from playwright.sync_api import sync_playwright

    out = Path(args.out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    domain = args.domain
    started = time.time()
    subprocess.Popen([sys.executable, __file__, "measure", domain, "--out", str(out)], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        page = browse_page(resolve(domain), out)
    except Exception as exc:
        page = {"blocked": True, "error": str(exc).splitlines()[0][:200]}
    with sync_playwright() as p:
        if page["blocked"]:
            page.update(title="", description="", headings=[], text="")
            for name in ("desktop.jpg", "full.jpg", "thumb.jpg", "mobile.jpg"):
                (out / name).unlink(missing_ok=True)
            report = lighthouse_report(out, 330)
            write_data_url(report["shots"]["desktop"].get("final"), out / "desktop")
            write_data_url(report["shots"]["mobile"].get("final"), out / "mobile")
            write_data_url(report["shots"]["desktop"].get("full"), out / "full")
            if (out / "desktop.jpg").exists():
                shutil.copy(out / "desktop.jpg", out / "thumb.jpg")
        shots = {name: next(out.glob(f"{name}.*"), None) for name in ("desktop", "mobile", "full")}
        shots["mobile"] = shots["mobile"] or shots["desktop"]
        shots["full"] = shots["full"] or shots["desktop"]
        if not shots["desktop"]:
            failures = lighthouse_report(out, 0)["failures"]
            reason = failures[0] if failures else page.get("error") or "the site blocks automated browsers"
            print(json.dumps({"domain": domain, "skip": True, "reason": f"couldn't load the site: {reason}"}, indent=2))
            return
        render(p, SHEET.format(**{k: data_url(v) for k, v in shots.items()}), out / "sheet.jpg", 2000, full_page=True)

    page = {
        "domain": domain,
        "started_at": started,
        "blocks_automated_browsers": page["blocked"],
        "title": page.get("title") or "",
        "headings": page.get("headings") or [],
        "text": (page.get("text") or "")[:1500],
    }
    (out / "page.json").write_text(json.dumps(page, indent=2))
    print(json.dumps({k: v for k, v in page.items() if k != "started_at"}, indent=2))


CARD = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap">
<style>
* {{ box-sizing: border-box; margin: 0; }}
body {{ width: 1200px; height: 630px; background: #0a0f1a; font-family: Geist, Inter, system-ui, sans-serif; color: #e6edf7; }}
.card {{ display: grid; grid-template-columns: 1fr 450px; height: 100%; }}
.left {{ padding: 56px 40px 48px 64px; display: flex; flex-direction: column; }}
.site {{ display: flex; align-items: center; gap: 14px; }}
.site img {{ width: 40px; height: 40px; border-radius: 9px; background: #fff; }}
.domain {{ font-size: 40px; font-weight: 600; letter-spacing: -0.03em; }}
.score {{ display: flex; align-items: baseline; gap: 14px; margin-top: 22px; }}
.num {{ font-size: 104px; font-weight: 700; line-height: 0.9; letter-spacing: -0.05em; color: {tone}; }}
.out {{ font-size: 36px; color: #7d8ba3; font-weight: 600; }}
.grade {{ font-size: 40px; font-weight: 700; color: {tone}; background: {tint}; border-radius: 12px; padding: 2px 16px; margin-left: 8px; }}
.judges {{ display: grid; gap: 10px; margin-top: auto; }}
.judge {{ display: grid; grid-template-columns: 112px 1fr; gap: 16px; align-items: baseline; }}
.who {{ display: flex; justify-content: space-between; font-size: 20px; color: #b6c2d6; }}
.who {{ font-size: 18px; }}
.who b {{ font-size: 22px; }}
.judge q {{ display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-size: 19px; line-height: 1.28; font-weight: 500; color: #e6edf7; }}
.brand {{ margin-top: 18px; font-size: 18px; color: #c6f432; }}
.right {{ padding: 48px 48px 48px 0; }}
.shot {{ width: 100%; height: 100%; border-radius: 16px; border: 1px solid #1e2a3f; background: #0f1626 left top / cover no-repeat url("{shot}"); }}
</style></head><body><div class="card">
<div class="left">
<div class="site"><img src="https://www.google.com/s2/favicons?domain={domain}&sz=128"><div class="domain">{domain}</div></div>
<div class="score"><div class="num">{score}</div><div class="out">/10</div><div class="grade">{letter}</div></div>
<div class="judges">{judges}</div>
<div class="brand">ratemyhomepage.pages.dev</div>
</div>
<div class="right"><div class="shot"></div></div>
</div></body></html>"""


def number(value, name, low, high):
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        fail(f"{name} must be an integer from {low} to {high}, got {value!r}")
    return value


def optional(value, name):
    return None if value is None else number(value, name, 0, 100)


def sentence(value, name, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\n" in value.strip():
        fail(f"{name} must be one sentence of at most {limit} characters")
    return value.strip()


def finish(args):
    from playwright.sync_api import sync_playwright

    out = Path(args.out)
    collected = json.loads((out / "page.json").read_text())
    if collected.get("domain") != args.domain:
        fail(f"no screenshots for {args.domain}; run shoot first")
    try:
        review = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        fail(f"the input on stdin isn't valid JSON ({exc})")

    given = review.get("judges")
    if not isinstance(given, dict) or set(given) != set(JUDGES):
        fail(f"judges must have exactly these keys: {', '.join(JUDGES)}")
    judges = {
        key: {
            "model": sentence(given[key].get("model"), f"{key} model", 80),
            "score": number(given[key].get("score"), f"{key} score", 1, 10),
            "roast": sentence(given[key].get("roast"), f"{key} roast"),
        }
        for key in JUDGES
    }
    score = round(sum(j["score"] for j in judges.values()) / len(judges), 1)
    report = lighthouse_report(out, 330)
    letter = next(g for minimum, g in GRADES if score >= minimum)
    result = {
        "domain": args.domain,
        "status": "done",
        "audited_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "score": score,
        "judges": judges,
        "mobile_speed": optional(report["scores"]["mobile"].get("performance"), "mobile_speed"),
        "desktop_speed": optional(report["scores"]["desktop"].get("performance"), "desktop_speed"),
        "accessibility": optional(report["scores"]["mobile"].get("accessibility"), "accessibility"),
        "seo": optional(report["scores"]["mobile"].get("seo"), "seo"),
        "agent_readiness": optional(review.get("ora_score"), "ora_score"),
        "blocks_automated_browsers": bool(collected.get("blocks_automated_browsers")),
        "minutes": max(1, round((time.time() - collected["started_at"]) / 60)),
    }
    if review.get("ora_summary"):
        result["agent_readiness_summary"] = sentence(review["ora_summary"], "ora_summary", 300)

    tone = TONES[letter]
    thumb = next((out / n for n in ("thumb.jpg", "desktop.jpg") if (out / n).exists()), None)
    card = CARD.format(
        tone=tone, tint=tone + "22", shot=data_url(thumb) if thumb else "", domain=html.escape(args.domain),
        score=score, letter=letter,
        judges="".join(
            f'<div class="judge"><div class="who">{name} <b style="color: {TONES[next(g for m, g in GRADES if judges[key]["score"] >= m)]}">'
            f'{judges[key]["score"]}</b></div><q>{html.escape(judges[key]["roast"])}</q></div>'
            for key, name in JUDGES.items()
        ),
    )
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
    print(json.dumps({"domain": args.domain, "score": score, "grade": letter, "bundle": str(bundle)}))


def main():
    parser = argparse.ArgumentParser(description="Rank one website for Rate My Homepage.")
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {
        "shoot": (shoot, "take screenshots and start Lighthouse in the background"),
        "finish": (finish, "average the judges' scores from stdin, add Lighthouse, and bundle the result"),
        "measure": (measure_site, "run Lighthouse; shoot starts this for you"),
    }
    for name, (_, help_text) in commands.items():
        command = sub.add_parser(name, help=help_text)
        command.add_argument("domain")
        command.add_argument("--out", help="output folder (default: /workspace/out/<domain>)")
    args = parser.parse_args()
    if not DOMAIN.match(args.domain):
        fail(f"bad domain {args.domain!r}")
    args.out = args.out or f"/workspace/out/{args.domain}"
    commands[args.command][0](args)


if __name__ == "__main__":
    main()
