"""
===============================================================================
Out-of-Band Locator Healer (v3, heal-service client)
===============================================================================
Runs failing pytest + Playwright tests, sends each failure's evidence to a heal service, applies the locator patch the
service returns, and re-runs to verify. Heals LOCATORS only -- never assertions or test intent. A failure it cannot make
pass is reverted and reported for a human (likely an app bug, not drift).

The service owns the model calls and the healing rules: it finds the broken call, picks the element, writes the locator by
the priority rules (test id > id > name > ... > text), adds language branches and decides healed or needs-human. This script
contains no model URL, model name, prompt or reply parsing. What it does (see utils/heal_client.py):
    - runs the suite and collects the failures from pytest's JUnit XML
    - per failure: reopens the failing route, collects the element inventory with the service's own probe script, sends it
      with the stack files, the language signals and (when recorded) the last green run's fingerprint
    - checks each candidate in the live page (exactly one match, the expected element) before editing anything
    - applies a patch only if its hash, path, span and replacement pass the safety checks, then re-runs the exact test and
      keeps the edit only if that test ran and passed and the service confirms
    - when the exact test passes its healed line but then fails at a different locator, reports that to the service and, if
      it confirms, keeps the edit and heals the next failure (up to LATER_ROUNDS more); a test left failing later is marked still_failing for review
    - prints every decision with its token usage and a run total, writes heal-summary.json, and with --open-pr commits only
      the healed files and records each healed locator in .heal/heals.json
    - on the next run, tells the service what became of every recorded heal (PR merged unchanged, edited, reverted, still
      open or closed; whether the test failed again; runs and days since) so it can report a kept rate and durability
      (utils/heal_followup.py; skipped quietly when `gh` or the service is unavailable)

This is the on-demand half of the overnight heal->PR orchestration: run it in CI/cron after the suite, optionally with
--open-pr to raise a single PR with the decisions and the tests it left untouched.

Usage:
    BASE_URL=... HEAL_SERVICE_URL=http://localhost:8765 [HEAL_SERVICE_TOKEN=...] [HEAL_STORAGE_STATE=auth.json] \\
        python scripts/heal.py [-k <name>] [--open-pr] [--max N]

Environment Variables:
    HEAL_SERVICE_URL: the heal service (required)
    HEAL_SERVICE_TOKEN: bearer token, when the service needs one
    HEAL_STORAGE_STATE: Playwright storage-state file, so the page is opened as a signed-in user (never sent)
    HEAL_VISION: off (default) | auto | on; auto and on send one masked viewport screenshot per failure (see utils/heal_client.py)
    HEAL_MASK: comma separated CSS selectors blacked out in that screenshot, besides every password input
    HEAL_TEST_ID_ATTRIBUTE: the project's test id attribute (default data-testid)
    HEAL_ARTIFACTS_DIR: where heal-summary.json goes (default test_artifacts)
    BASE_URL: the app under test

Author: PMAC
Site: The Internet (https://the-internet.herokuapp.com)
===============================================================================
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # `python scripts/heal.py` puts scripts/ first, not the repo

from utils.heal_client import (  # noqa: E402
    HealSettings, Healer, ServiceClient, run_total, validate_replacement, vision_mode,
)
from utils.heal_followup import follow_up, pr_url_from, record_heals  # noqa: E402

LAST_CASES = []        # every test case of the last run_suite() (the follow-up counts runs and failures from it)
LATER_ROUNDS = 3       # further heals of one test after its first, each for the next locator it stops at

__all__ = ["run_pytest", "run_suite", "verify_run", "verify_passed", "validate_replacement", "working_tree_dirty", "heal_failures",
           "write_summary", "build_pr_body", "commit_lines", "md_escape", "follow_up_heals", "open_pr", "main"]


def run_pytest(keyword=None):
    """
    Run pytest (optionally -k filtered). Returns (returncode, cases) where each
    case is {name, classname, outcome, error}; outcome is passed|failed|skipped.
    cases is empty when nothing ran or the JUnit report could not be produced.
    HEAL_RUN is set for the child so the fingerprint plugin records nothing during a heal.
    """
    out = os.path.join(tempfile.mkdtemp(prefix="heal-"), "report.xml")
    cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--reruns", "0", f"--junit-xml={out}"]
    if keyword:
        cmd += ["-k", keyword]
    proc = subprocess.run(cmd, env={**os.environ, "HEAL_RUN": "1"}, capture_output=True)
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
    """Return failing {name, classname, error} entries from a run (all its cases are kept in LAST_CASES)."""
    _, cases = run_pytest(keyword)
    LAST_CASES[:] = cases
    return [c for c in cases if c["outcome"] == "failed"]


def verify_run(test, runner=run_pytest):
    """
    (passed, failure) for a re-run of the exact target test. `passed` is True only if that test ran AND passed AND pytest
    exited cleanly; an empty selection, collection error or missing report is NOT a pass. `failure` is the target's failed
    case ({name, classname, outcome, error}, as run_suite returns them) or None when it passed or never ran to a failure.
    """
    returncode, cases = runner(test["name"].split("[", 1)[0])
    ran = [c for c in cases if c["name"] == test["name"] and c["classname"] == test.get("classname")]
    passed = returncode == 0 and bool(ran) and all(c["outcome"] == "passed" for c in ran)
    return passed, None if passed else next((c for c in ran if c["outcome"] == "failed"), None)


def verify_passed(test, runner=run_pytest):
    """True only if the exact target test ran AND passed AND pytest exited cleanly (see verify_run)."""
    return verify_run(test, runner)[0]


def working_tree_dirty():
    """True if any tracked file has uncommitted changes."""
    out = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True)
    return bool(out.strip())


def heal_test(failure, healer, decisions, healed):
    """
    Heal one failing test, recording each heal as its own decision. A heal the service kept because the test then stopped
    at a different locator (reason later_locator) is followed by another heal of the next failure, up to LATER_ROUNDS more.
    When the chain ends on something that cannot be healed, the earlier heals stay kept and the last kept one is marked
    still_failing, so a person reviews that test.
    """
    kept_last, rounds = None, 0
    while True:
        d = healer.heal(failure)
        later = d.pop("later_failure", None)           # the re-run's traceback is for the next round, not the record
        decisions.append(d)
        if kept_last is not None and d["outcome"] != "healed":
            kept_last.update(still_failing=True, still_failing_why=f"the next failure was not healed ({d['outcome']}): "
                                                                  f"{d.get('why') or d.get('reason') or 'no reason given'}")
        if d["outcome"] != "healed":
            return
        healed.append(d)
        if d.get("reason") != "later_locator":
            return
        kept_last = d
        if not later or rounds >= LATER_ROUNDS:
            d.update(still_failing=True, still_failing_why=(
                f"stopped after {LATER_ROUNDS} further heals, the test still fails at a later locator" if later
                else "the test still fails at a later locator"))
            return
        rounds += 1
        failure = later


def heal_failures(fails, healer, max_n, verify=verify_passed):
    """
    The decisions for failing tests, one per heal (a test healed in several rounds has several). Failures past `max_n` are
    recorded as needs_human, never dropped. A failure a previous heal already fixed (a page object shared by several
    tests) is confirmed by re-running it, not healed twice.
    """
    decisions, healed = [], []
    for f in fails[:max_n]:
        if healed and verify(f):
            first = healed[0]
            decisions.append({"test": f["name"], "outcome": "healed", "file": first["file"], "from": first["from"],
                              "to": first["to"], "files": first.get("files", []), "usage": {},
                              "source": f"same fix as {first['test']} (shared locator), re-run passed"})
            continue
        heal_test(f, healer, decisions, healed)
    decisions += [{"test": f["name"], "outcome": "needs_human", "reason": "beyond_max",
                   "why": f"not attempted: beyond --max {max_n}"} for f in fails[max_n:]]
    return decisions


def write_summary(decisions, started, run_id, directory=None):
    """Write heal-summary.json (counts, usage total, every decision) into the test artifacts dir; returns its path."""
    directory = Path(directory or os.getenv("HEAL_ARTIFACTS_DIR", "test_artifacts"))
    directory.mkdir(parents=True, exist_ok=True)
    counts = {k: sum(1 for d in decisions if d["outcome"] == k) for k in ("healed", "needs_human", "not_drift")}
    summary = {"run_id": run_id, "mode": "heal", "started": started, "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "failures": len({d["test"] for d in decisions}), "counts": counts,
               "kept_still_failing": sum(1 for d in decisions if d.get("still_failing")), "usage": run_total(decisions), "decisions": decisions}
    path = directory / "heal-summary.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _tokens(d):
    u = d.get("usage") or {}
    return f"tokens {u.get('input_tokens', 0)} in / {u.get('output_tokens', 0)} out, {u.get('calls', 0)} call(s)"


def print_decisions(decisions):
    print("\n[heal] decisions:")
    for d in decisions:
        if d["outcome"] == "healed":
            print(f"  [healed] {d['test']}: {d['file']}: {d['from']} -> {d['to']}  ({_tokens(d)})")
            if d.get("still_failing"):
                print(f"    kept, test still fails later: {d.get('still_failing_why')}")
        else:
            reason = f" [{d['reason']}]" if d.get("reason") else ""
            print(f"  [{d['outcome']}]{reason} {d['test']}: {d.get('why')}  ({_tokens(d)})")
    t = run_total(decisions)
    print(f"[heal] run total: {t['calls']} model call(s), {t['input_tokens']} input / {t['output_tokens']} output tokens, "
          f"{t['images']} image(s)")


_MD_SPECIAL = set("\\`*_[]()<>#|!~@&{}")


def one_line(value, limit=300):
    """`value` as text on one line: control characters and line breaks become a space, capped (it came from the service)."""
    text = "".join(" " if (ord(c) < 32 or ord(c) == 127 or 0x80 <= ord(c) < 0xA0 or c in "\u2028\u2029") else c
                   for c in str(value if value is not None else ""))
    return " ".join(text.split())[:limit]


def md_escape(value, limit=300):
    """`value` safe to put in a markdown line: one line, and every character that makes a link, an image, HTML, a heading,
    a mention or emphasis is escaped (a service string cannot add a link or a section to a PR)."""
    return "".join("&#64;" if c == "@" else "&lt;" if c == "<" else "&gt;" if c == ">" else "&amp;" if c == "&"
                   else "\\" + c if c in _MD_SPECIAL else c for c in one_line(value, limit))


def md_code(value, limit=300):
    """`value` as an inline code span whose fence is longer than any backtick run inside it."""
    text = one_line(value, limit)
    runs = re.findall(r"`+", text)
    if not runs:
        return f"`{text}`"
    fence = "`" * (max(len(r) for r in runs) + 1)
    return f"{fence} {text} {fence}"


def commit_lines(healed):
    """One single-line entry per healed test for the commit body (no service text can start a new line or a trailer)."""
    return [f"- {one_line(d['test'], 200)}: {one_line(d['from'], 200)} -> {one_line(d['to'], 200)}" for d in healed]


def build_pr_body(healed, other):
    """The PR description. Every string that came from the service or the test run is escaped."""
    body = "Automated locator healing (out-of-band).\n\n## Healed (locators only, intent preserved)\n"
    body += "\n".join(f"- **{md_escape(d['test'])}** -- {md_code(d['from'])} -> {md_code(d['to'])} "
                      f"({md_escape(d.get('why') or d.get('source'))})" for d in healed)
    still = [d for d in healed if d.get("still_failing")]
    if still:
        body += "\n\n## Kept, test still fails later (review)\n" + "\n".join(
            f"- **{md_escape(d['test'])}** -- {md_escape(d.get('still_failing_why'))}" for d in still)
    if other:
        body += "\n\n## Needs human review (not touched)\n" + "\n".join(
            f"- **{md_escape(d['test'])}** -- {md_escape(d.get('why'))}" for d in other)
    return body


def open_pr(healed, other):
    """Branch, commit ONLY the healed files, push, and open one PR listing the decisions."""
    branch = f"heal/{time.strftime('%Y-%m-%d')}-{int(time.time()):x}"
    subprocess.check_call(["git", "checkout", "-b", branch])
    healed_files = sorted({f for d in healed for f in (d.get("files") or [d["file"]])})
    # Stage and commit ONLY the files this run healed.
    subprocess.check_call(["git", "add", "--", *healed_files])
    subprocess.check_call(["git", "commit", "-qm",
                           f"fix(heal): update {len(healed)} drifted locator(s)\n\n" + "\n".join(commit_lines(healed)),
                           "--", *healed_files])
    subprocess.check_call(["git", "push", "-q", "-u", "origin", branch])
    out = subprocess.check_output(["gh", "pr", "create", "--base", "main", "--head", branch,
                                   "--title", f"Locator healing -- {len(healed)} fixed, {len(other)} for review",
                                   "--body", build_pr_body(healed, other)], text=True)
    print(out.strip())
    return pr_url_from(out)


def follow_up_heals(service, cases, root=None):
    """Tell the service what became of every heal recorded by an earlier --open-pr run. Never raises: this is bookkeeping."""
    try:
        sent = follow_up(Path(root or Path.cwd()), service, cases)
    except Exception as e:                               # gh, the disk, the service: skip, the run goes on
        print(f"[heal] follow-up skipped ({type(e).__name__})")
        return []
    for s in sent:
        print(f"[heal] follow-up: {s['test']}: PR {s['pr_state'].replace('_', ' ')}, "
              f"{s['runs_since']} run(s) and {s['days_since']} day(s) since the heal"
              + (", failed again" if s["failed_again"] else ""))
    return sent


def main():
    settings = HealSettings.from_env()
    if not settings.url:
        print("Set HEAL_SERVICE_URL (the heal service, for example http://localhost:8765).")
        sys.exit(2)
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", "--grep", default=None, help="pytest -k keyword to scope tests")
    ap.add_argument("--open-pr", action="store_true")
    ap.add_argument("--max", type=int, default=10)
    args = ap.parse_args()
    if vision_mode(settings) != "off":
        print(f"[heal] HEAL_VISION={settings.vision}: one masked viewport screenshot is sent per failure "
              "(password inputs and HEAL_MASK selectors are blacked out).")
    elif settings.vision != "off":
        print(f"[heal] HEAL_VISION={settings.vision!r} is not off, auto or on: running with vision off, no screenshot is taken.")

    if args.open_pr and working_tree_dirty():
        print("[heal] --open-pr needs a clean working tree (tracked files have local changes); "
              "commit or stash them first.")
        sys.exit(2)

    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    run_id = uuid.uuid4().hex[:12]
    print(f"[heal] running suite{f' (-k {args.grep})' if args.grep else ''}...")
    LAST_CASES.clear()
    fails = run_suite(args.grep)
    service = ServiceClient(settings.url, settings.token)
    follow_up_heals(service, list(LAST_CASES))
    if not fails:
        print("[heal] no failures -- nothing to heal.")
        return
    print(f"[heal] {len(fails)} failing test(s).")

    healer = Healer(service, settings, verify_run, run_id=run_id)
    decisions = heal_failures(fails, healer, args.max)

    print_decisions(decisions)
    path = write_summary(decisions, started, run_id)
    healed = [d for d in decisions if d["outcome"] == "healed"]
    other = [d for d in decisions if d["outcome"] != "healed"]
    if args.open_pr and healed:
        pr_url = open_pr(healed, other)
        try:
            if pr_url and record_heals(Path.cwd(), healed, pr_url, run_id=run_id):
                print("[heal] recorded the healed locators for follow-up in .heal/heals.json")
        except Exception as e:                           # bookkeeping: the PR is already open
            print(f"[heal] could not record the heals for follow-up ({type(e).__name__})")
    still = sum(1 for d in healed if d.get("still_failing"))
    print(f"\n[heal] done: {len(healed)} healed, {len(other)} for human review"
          + (f", {still} kept but the test still fails later" if still else "") + f". Summary: {path}")


if __name__ == "__main__":
    main()
