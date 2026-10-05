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
    HEAL_BASE_URL   e.g. https://openrouter.ai/api/v1 | http://localhost:11434/v1
    HEAL_MODEL      e.g. your-model-name
    HEAL_API_KEY    optional (omit for a local endpoint)

Usage:
    BASE_URL=... HEAL_BASE_URL=... HEAL_MODEL=... [HEAL_STORAGE_STATE=auth.json] \\
        python scripts/heal.py [-k <name>] [--open-pr] [--max N]

Author: PMAC
Site: The Internet (https://the-internet.herokuapp.com)
===============================================================================
"""
import argparse
import ast
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

BASE_URL = os.getenv("BASE_URL", "http://localhost:7080")
HEAL_BASE_URL = os.getenv("HEAL_BASE_URL")
HEAL_MODEL = os.getenv("HEAL_MODEL")
HEAL_API_KEY = os.getenv("HEAL_API_KEY", "")
# Optional Playwright storage-state file (JSON) so the snapshot of an
# authenticated page is taken as a logged-in user, not an anonymous visitor.
HEAL_STORAGE_STATE = os.getenv("HEAL_STORAGE_STATE")
SOURCE_DIRS = ("pages", "tests", "utils")

# A replacement may only be a chain of these Playwright locator calls on the
# same receiver as the expression it replaces, with literal arguments.
ALLOWED_LOCATOR_METHODS = {
    "locator", "get_by_role", "get_by_label", "get_by_text", "get_by_placeholder",
    "get_by_test_id", "get_by_alt_text", "get_by_title", "first", "last", "nth", "filter",
}

SELECTOR_RE = re.compile(
    r"""locator\(['"]([^'"]+)['"]\)|get_by_\w+\(['"]([^'"]+)['"]\)|waiting for (?:locator )?['"]([^'"]+)['"]"""
)


def run_pytest(keyword=None):
    """
    Run pytest (optionally -k filtered). Returns (returncode, cases) where each
    case is {name, classname, outcome, error}; outcome is passed|failed|skipped.
    cases is empty when nothing ran or the JUnit report could not be produced.
    """
    out = os.path.join(tempfile.mkdtemp(prefix="heal-"), "report.xml")
    cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--reruns", "0", f"--junit-xml={out}"]
    if keyword:
        cmd += ["-k", keyword]
    proc = subprocess.run(cmd, env={**os.environ}, capture_output=True)
    cases = []
    try:
        root = ET.parse(out).getroot()
    except (ET.ParseError, FileNotFoundError):
        return proc.returncode, cases
    for tc in root.iter("testcase"):
        bad = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
        if bad is not None:
            outcome, msg = "failed", (bad.get("message") or "") + "\n" + (bad.text or "")
        elif tc.find("skipped") is not None:
            outcome, msg = "skipped", ""
        else:
            outcome, msg = "passed", ""
        cases.append({"name": tc.get("name"), "classname": tc.get("classname"),
                      "outcome": outcome, "error": msg})
    return proc.returncode, cases


def run_suite(keyword=None):
    """Return failing {name, classname, error} entries from a run."""
    _, cases = run_pytest(keyword)
    return [c for c in cases if c["outcome"] == "failed"]


def verify_passed(test, runner=run_pytest):
    """
    True only if the exact target test ran AND passed AND pytest exited cleanly.
    An empty selection, collection error or missing report is NOT a pass.
    """
    returncode, cases = runner(test["name"].split("[", 1)[0])
    ran = [c for c in cases if c["name"] == test["name"] and c["classname"] == test.get("classname")]
    return returncode == 0 and bool(ran) and all(c["outcome"] == "passed" for c in ran)


def broken_selector_from(error):
    """Pull the first concrete selector literal out of a Playwright error message."""
    m = SELECTOR_RE.search(error)
    if not m:
        return None
    return next((g for g in m.groups() if g), None)


def locate_in_source(selector, root=None):
    """
    Find the single source site of a ``page.locator('<selector>')`` call.

    Scans *.py under SOURCE_DIRS in-process (literal match, no grep/regex on the
    selector, cross-platform). Returns {file, src, start, end, call, route}, or
    {"ambiguous": N} when the same locator appears more than once (replacing it
    blindly could change an unrelated use), or None when not found.
    """
    root = Path(root) if root else Path.cwd()
    call_re = re.compile(
        r"(?:self\.)?page\.locator\(\s*(['\"])" + re.escape(selector) + r"\1\s*\)"
    )
    sites = []
    for d in SOURCE_DIRS:
        for path in sorted((root / d).rglob("*.py")):
            src = path.read_text(encoding="utf-8")
            for m in call_re.finditer(src):
                sites.append((path, src, m))
    if not sites:
        return None
    if len(sites) > 1:
        return {"ambiguous": len(sites)}
    path, src, m = sites[0]
    route_m = re.search(r'self\.url\s*=\s*f?"[^"]*BASE_URL\}?([^"]*)"', src)
    return {
        "file": str(path.relative_to(root)),
        "src": src,
        "start": m.start(),
        "end": m.end(),
        "call": m.group(0),
        "route": route_m.group(1) if route_m else "/",
    }


def validate_replacement(proposed, original):
    """
    Return the replacement if it is a safe drop-in for ``original``, else None.
    Must be a single-line expression that is a chain of approved Playwright
    locator calls with literal arguments, rooted at the same receiver
    (``page`` / ``self.page``) as the original.
    """
    if not proposed or "\n" in proposed or ";" in proposed:
        return None
    try:
        tree = ast.parse(proposed, mode="eval").body
        original_tree = ast.parse(original, mode="eval").body
    except SyntaxError:
        return None

    def receiver(node):
        while isinstance(node, (ast.Call, ast.Attribute)):
            node = node.func if isinstance(node, ast.Call) else node.value
        return node

    def base_receiver(node):
        # the object the first locator method is called on, e.g. self.page
        chain = []
        while isinstance(node, (ast.Call, ast.Attribute)):
            chain.append(node)
            node = node.func if isinstance(node, ast.Call) else node.value
        for n in reversed(chain):
            if isinstance(n, ast.Attribute) and n.attr in ALLOWED_LOCATOR_METHODS:
                return ast.unparse(n.value)
        return None

    if not isinstance(tree, (ast.Call, ast.Attribute)) or not isinstance(receiver(tree), ast.Name):
        return None
    if base_receiver(tree) != base_receiver(original_tree):
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            # attribute access is allowed only for approved methods and the receiver chain
            if node.attr not in ALLOWED_LOCATOR_METHODS and ast.unparse(node) not in {"self.page"}:
                return None
        elif isinstance(node, ast.Call):
            for arg in [*node.args, *(k.value for k in node.keywords)]:
                if not isinstance(arg, ast.Constant):
                    return None
        elif not isinstance(node, (ast.Name, ast.Constant, ast.Load, ast.keyword)):
            return None
    return proposed


def aria_snapshot(route):
    """Capture the live accessibility snapshot of a route for grounding."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(
                base_url=BASE_URL,
                **({"storage_state": HEAL_STORAGE_STATE} if HEAL_STORAGE_STATE else {}),
            )
            page = context.new_page()
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


def apply_replacement(loc, proposed):
    """Source text with ONLY the located occurrence replaced."""
    return loc["src"][: loc["start"]] + proposed + loc["src"][loc["end"]:]


def working_tree_dirty():
    """True if any tracked file has uncommitted changes."""
    out = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True)
    return bool(out.strip())


def main():
    if not HEAL_BASE_URL or not HEAL_MODEL:
        print("Set HEAL_BASE_URL and HEAL_MODEL (OpenAI-compatible endpoint + model id).")
        sys.exit(2)
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", "--grep", default=None, help="pytest -k keyword to scope tests")
    ap.add_argument("--open-pr", action="store_true")
    ap.add_argument("--max", type=int, default=10)
    args = ap.parse_args()

    if args.open_pr and working_tree_dirty():
        print("[heal] --open-pr needs a clean working tree (tracked files have local changes); "
              "commit or stash them first.")
        sys.exit(2)

    print(f"[heal] running suite{f' (-k {args.grep})' if args.grep else ''}...")
    fails = run_suite(args.grep)
    if not fails:
        print("[heal] no failures -- nothing to heal.")
        return
    print(f"[heal] {len(fails)} failing test(s).")
    decisions = []

    for f in fails[args.max:]:
        decisions.append({"test": f["name"], "outcome": "human",
                          "why": f"not attempted: beyond --max {args.max}"})

    for f in fails[: args.max]:
        selector = broken_selector_from(f["error"])
        if not selector:
            decisions.append({"test": f["name"], "outcome": "human",
                              "why": "no broken selector in the error -- looks like a logic/app failure, not locator drift"})
            continue
        loc = locate_in_source(selector)
        if loc and loc.get("ambiguous"):
            decisions.append({"test": f["name"], "outcome": "human",
                              "why": f"selector {selector} appears {loc['ambiguous']} times in source -- "
                                     "ambiguous which use broke, not auto-edited"})
            continue
        if not loc:
            decisions.append({"test": f["name"], "outcome": "human",
                              "why": f"selector {selector} not found as a .locator() call in source (dynamic/semantic?)"})
            continue
        snapshot = aria_snapshot(loc["route"])
        proposed = validate_replacement(propose_replacement(loc["call"], snapshot), loc["call"])
        if not proposed or proposed == loc["call"]:
            decisions.append({"test": f["name"], "outcome": "human",
                              "why": "model produced no usable (valid, safe) replacement"})
            continue
        # Replace only the diagnosed occurrence (by span), not every identical string.
        patched = apply_replacement(loc, proposed)
        Path(loc["file"]).write_text(patched, encoding="utf-8")
        if not verify_passed(f):
            Path(loc["file"]).write_text(loc["src"], encoding="utf-8")  # revert -- never leave a non-passing change
            decisions.append({"test": f["name"], "outcome": "human",
                              "why": f'proposed "{proposed}" did not make the test run and pass -- reverted; likely an app bug'})
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
        healed_files = sorted({d["file"] for d in healed})
        # Stage and commit ONLY the files this run healed.
        subprocess.check_call(["git", "add", "--", *healed_files])
        subprocess.check_call(["git", "commit", "-qm",
                               f"fix(heal): update {len(healed)} drifted locator(s)\n\n" + "\n".join(body_lines),
                               "--", *healed_files])
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
