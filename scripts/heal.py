"""
===============================================================================
Out-of-Band Locator Healer (v2, CLI mode)
===============================================================================
Runs failing pytest + Playwright tests, reproduces each failure in a real
browser to read the live accessibility snapshot, asks a configurable model for a
resilient semantic locator, applies it, and re-runs to verify. Heals LOCATORS
only -- never assertions or test intent. A failure it cannot make pass is
reverted and reported for a human (likely an app bug, not drift).

This is the on-demand half of the overnight heal->PR orchestration: run it in
CI/cron after the suite, optionally with --open-pr to raise a single PR with the
decisions and the tests it left untouched.

Model is provider-agnostic via an OpenAI-compatible endpoint:
    HEAL_BASE_URL   e.g. https://openrouter.ai/api/v1 | http://192.168.1.47:3025/v1
    HEAL_MODEL      e.g. ollama@localhost/qwen3.8-27b:latest
    HEAL_API_KEY    optional (omit for a local/fleet proxy)
Route fleet models through their proxy so usage is attributed; never call a
model endpoint directly.

Usage:
    BASE_URL=... HEAL_BASE_URL=... HEAL_MODEL=... \\
        python scripts/heal.py [-k <name>] [--open-pr] [--max N]

Author: PMAC
Site: The Internet (https://the-internet.herokuapp.com)
===============================================================================
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import requests
from playwright.sync_api import sync_playwright

BASE_URL = os.getenv("BASE_URL", "http://localhost:7080")
HEAL_BASE_URL = os.getenv("HEAL_BASE_URL")
HEAL_MODEL = os.getenv("HEAL_MODEL")
HEAL_API_KEY = os.getenv("HEAL_API_KEY", "")

SELECTOR_RE = re.compile(
    r"""locator\(['"]([^'"]+)['"]\)|get_by_\w+\(['"]([^'"]+)['"]\)|waiting for (?:locator )?['"]([^'"]+)['"]"""
)


def run_suite(keyword=None):
    """Run the suite (optionally -k filtered) and return failing (test_name, message) pairs."""
    out = os.path.join(tempfile.mkdtemp(prefix="heal-"), "report.xml")
    cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--reruns", "0", f"--junit-xml={out}"]
    if keyword:
        cmd += ["-k", keyword]
    subprocess.run(cmd, env={**os.environ}, capture_output=True)  # nonzero exit on failures is expected
    fails = []
    try:
        root = ET.parse(out).getroot()
    except (ET.ParseError, FileNotFoundError):
        return fails
    for tc in root.iter("testcase"):
        bad = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
        if bad is not None:
            msg = (bad.get("message") or "") + "\n" + (bad.text or "")
            fails.append({"name": tc.get("name"), "error": msg})
    return fails


def broken_selector_from(error):
    """Pull the first concrete selector literal out of a Playwright error message."""
    m = SELECTOR_RE.search(error)
    if not m:
        return None
    return next((g for g in m.groups() if g), None)


def locate_in_source(selector):
    """Find the source file, the full locator call, and the page route for a selector."""
    try:
        hits = subprocess.check_output(
            ["grep", "-rln", "--include=*.py", selector, "pages", "tests", "utils"], text=True
        ).strip()
    except subprocess.CalledProcessError:
        return None
    path = hits.splitlines()[0] if hits else None
    if not path:
        return None
    src = open(path).read()
    route_m = re.search(r'self\.url\s*=\s*f?"[^"]*BASE_URL\}?([^"]*)"', src)
    call_m = re.search(r'(?:self\.)?page\.locator\(\s*[\'"]' + re.escape(selector) + r'[\'"]\s*\)', src)
    return {
        "file": path,
        "src": src,
        "route": route_m.group(1) if route_m else "/",
        "call": call_m.group(0) if call_m else None,
    }


def aria_snapshot(route):
    """Capture the live accessibility snapshot of a route for grounding."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(base_url=BASE_URL)
            page.goto(route)
            return page.locator("body").aria_snapshot()
        finally:
            browser.close()


def propose_replacement(call, snapshot):
    """Ask the model to replace an exact locator expression (semantic, intent-preserving)."""
    prompt = (
        "You are a Playwright (Python) test healer. A locator broke after a UI change.\n"
        f"Replace exactly this locator expression:\n  {call}\n\n"
        f"Live page accessibility snapshot:\n{snapshot}\n\n"
        "Return ONLY the drop-in replacement expression (same leading receiver, e.g. "
        "\"self.page.get_by_label('Username')\"). No prose, no code fence, no trailing "
        "characters. Prefer a resilient semantic locator (get_by_role/get_by_label/"
        "get_by_test_id over raw CSS/id). Target the SAME element -- never change the test's intent."
    )
    headers = {"Content-Type": "application/json"}
    if HEAL_API_KEY:
        headers["Authorization"] = f"Bearer {HEAL_API_KEY}"
    resp = requests.post(
        f"{HEAL_BASE_URL}/chat/completions",
        headers=headers,
        json={"model": HEAL_MODEL, "messages": [{"role": "user", "content": prompt}],
              "temperature": 0, "max_tokens": 200},
        timeout=180,
    )
    out = resp.json()["choices"][0]["message"]["content"].strip()
    out = re.sub(r"```[a-z]*\n?|```", "", out).strip().splitlines()[0].strip()
    return out


def main():
    if not HEAL_BASE_URL or not HEAL_MODEL:
        print("Set HEAL_BASE_URL and HEAL_MODEL (OpenAI-compatible endpoint + model id).")
        sys.exit(2)
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", "--grep", default=None, help="pytest -k keyword to scope tests")
    ap.add_argument("--open-pr", action="store_true")
    ap.add_argument("--max", type=int, default=10)
    args = ap.parse_args()

    print(f"[heal] running suite{f' (-k {args.grep})' if args.grep else ''}...")
    fails = run_suite(args.grep)
    if not fails:
        print("[heal] no failures -- nothing to heal.")
        return
    print(f"[heal] {len(fails)} failing test(s).")
    decisions = []

    for f in fails[: args.max]:
        selector = broken_selector_from(f["error"])
        if not selector:
            decisions.append({"test": f["name"], "outcome": "human",
                              "why": "no broken selector in the error -- looks like a logic/app failure, not locator drift"})
            continue
        loc = locate_in_source(selector)
        if not loc or not loc["call"]:
            decisions.append({"test": f["name"], "outcome": "human",
                              "why": f"selector {selector} not found as a .locator() call in source (dynamic/semantic?)"})
            continue
        snapshot = aria_snapshot(loc["route"])
        proposed = propose_replacement(loc["call"], snapshot)
        if not proposed or proposed == loc["call"]:
            decisions.append({"test": f["name"], "outcome": "human", "why": "model produced no usable replacement"})
            continue
        with open(loc["file"], "w") as fh:
            fh.write(loc["src"].replace(loc["call"], proposed))
        still_fails = any(x["name"] == f["name"] for x in run_suite(f["name"]))
        if still_fails:
            with open(loc["file"], "w") as fh:
                fh.write(loc["src"])  # revert -- never leave a non-passing change
            decisions.append({"test": f["name"], "outcome": "human",
                              "why": f'proposed "{proposed}" did not make the test pass -- reverted; likely an app bug'})
        else:
            decisions.append({"test": f["name"], "outcome": "healed", "file": loc["file"],
                              "from": loc["call"], "to": proposed, "source": f'aria snapshot of {loc["route"]}'})

    print("\n[heal] decisions:")
    for d in decisions:
        print("  " + str(d))
    healed = [d for d in decisions if d["outcome"] == "healed"]
    human = [d for d in decisions if d["outcome"] == "human"]

    if args.open_pr and healed:
        import time
        branch = f"heal/{time.strftime('%Y-%m-%d')}-{int(time.time()):x}"
        subprocess.check_call(["git", "checkout", "-b", branch])
        body_lines = [f"- {d['test']}: {d['from']} -> {d['to']}" for d in healed]
        subprocess.check_call(["git", "commit", "-aqm",
                               f"fix(heal): update {len(healed)} drifted locator(s)\n\n" + "\n".join(body_lines)])
        subprocess.check_call(["git", "push", "-q", "-u", "origin", branch])
        pr_body = "Automated locator healing (out-of-band).\n\n## Healed (locators only, intent preserved)\n"
        pr_body += "\n".join(f"- **{d['test']}** -- `{d['from']}` -> `{d['to']}` (grounded in {d['source']})" for d in healed)
        if human:
            pr_body += "\n\n## Needs human review (not touched)\n" + "\n".join(
                f"- **{d['test']}** -- {d['why']}" for d in human)
        subprocess.check_call(["gh", "pr", "create", "--base", "main", "--head", branch,
                               "--title", f"Locator healing -- {len(healed)} fixed, {len(human)} for review",
                               "--body", pr_body])

    print(f"\n[heal] done: {len(healed)} healed, {len(human)} for human review.")


if __name__ == "__main__":
    main()
