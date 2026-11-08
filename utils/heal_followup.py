"""
===============================================================================
Heal Follow-Up (what happened to a healed locator after its pull request)
===============================================================================
A heal is only worth what a person keeps. When `scripts/heal.py --open-pr` raises a PR, this module records each healed
locator in `.heal/heals.json`: `{heal_id, file, from, to, test, pr_url}` plus when it was opened. On the next `scripts/heal.py`
run, for each recorded heal it works out, from git and from the run just made, what became of it and tells the heal service
(`POST /v1/heals/{id}/followup`), which turns it into the service's kept rate, durability and escaped-wrong-heal numbers:

    pr_state    open              the PR is still open
                closed_unmerged   the PR was closed without merging
                merged_unchanged  merged, and the healed line in the file is still `to`
                edited            merged, and the line is neither `to` nor `from` any more (a person changed it)
                reverted          merged, and the line is back to `from`
    failed_again  the test failed in a run made after the heal (once true it stays true)
    runs_since    runs in which the test ran since the heal, days_since    whole days since the PR was opened

Features:
    ✓ Skips quietly when it cannot know: `gh` missing or failing, an unreadable file, a service that is down. A follow-up
      never fails the run (the caller wraps it as well) and never edits a source file
    ✓ A PR address must match in full (not just at its ends) and name github.com, or the host in HEAL_GH_HOST; one bad entry
      (an exception while handling it) never stops the others
    ✓ The record file lives in the git-ignored `.heal/` folder (HEAL_DIR), is written atomically and is treated as untrusted
      input: malformed entries are dropped, a PR address must be an https pull request URL before it is handed to `gh`
      (as an argument list, never a shell), and a file path must sit under the source roots with every symlink followed
    ✓ Counts runs and failures even while `gh` is unavailable, so the numbers are right when it comes back
    ✓ An entry is finished when its PR closed unmerged, the merge was reverted, a service no longer has the heal (retention),
      or it has lived 10 runs and 30 days with a durability answer sent; finished entries are dropped after 60 days
    ✓ The service keeps a heal for HEAL_RETENTION_DAYS (default 14): durability needs the service's retention set to at least
      31 days, or its follow-up answer is a 404 and the entry is finished early

Environment Variables:
    HEAL_SERVICE_URL, HEAL_SERVICE_TOKEN: the service (see utils/heal_client.py)
    HEAL_GH_HOST: the one host a PR address may name instead of github.com (a GitHub Enterprise host)
    HEAL_REPO: the repo name sent with a follow-up (the service refuses one that is not the heal record's)
    HEAL_DIR: where `.heal/` lives (see utils/heal_fingerprints.py)
    HEAL_SOURCE_ROOTS: source roots a recorded file must sit under

Author: PMAC
===============================================================================
"""
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from utils.heal_client import HealServiceError, read_text_file, within_roots
from utils.heal_fingerprints import heal_dir, source_roots

FILE_NAME = "heals.json"
DAY = 86400
DURABLE_RUNS, DURABLE_DAYS = 10, 30
KEEP_FINISHED_DAYS = 60
MAX_ENTRIES = 500
DEFAULT_HOST = "github.com"
_HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")
_PR_PATH = r"/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/pull/[0-9]+"
_HEAL_ID = re.compile(r"h_[A-Za-z0-9]{1,64}")
_RUN_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
GH_STATES = {"OPEN": "open", "CLOSED": "closed_unmerged", "MERGED": "merged"}


def pr_host(env: Optional[Dict[str, str]] = None) -> str:
    """The one host a PR address may name: github.com, or HEAL_GH_HOST when the operator sets it (a GitHub Enterprise host)."""
    value = (env if env is not None else os.environ).get("HEAL_GH_HOST", "").strip().lower()
    return value if value and _HOST.fullmatch(value) else DEFAULT_HOST


def is_pr_url(url: Any, env: Optional[Dict[str, str]] = None) -> bool:
    """True for `https://<host>/<owner>/<repo>/pull/<n>` on the pinned host, matched in full (a trailing newline or any other
    tail is not a PR address)."""
    return isinstance(url, str) and re.fullmatch("https://" + re.escape(pr_host(env)) + _PR_PATH, url) is not None


def heals_path(root: Path, env: Optional[Dict[str, str]] = None) -> Path:
    return heal_dir(root, env) / FILE_NAME


def _text(value: Any, limit: int = 2000) -> Optional[str]:
    return value if isinstance(value, str) and 0 < len(value) <= limit else None


def _entry(raw: Any, env: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    """A well-formed entry from the file, or None. The file is a cache a person (or a bad merge) may have changed."""
    if not isinstance(raw, dict):
        return None
    heal_id, file, test, url = (_text(raw.get(k), n) for k, n in (("heal_id", 80), ("file", 300), ("test", 500), ("pr_url", 300)))
    old, new = _text(raw.get("from")), _text(raw.get("to"))
    opened = raw.get("opened_at")
    if not (heal_id and _HEAL_ID.fullmatch(heal_id) and file and old and new and test and is_pr_url(url, env)
            and isinstance(opened, (int, float)) and not isinstance(opened, bool)):
        return None
    repo, run_id = _text(raw.get("repo"), 200) or "", _text(raw.get("run_id"), 64) or ""
    if run_id and not _RUN_ID.fullmatch(run_id):
        run_id = ""
    runs = raw.get("runs")
    return {"heal_id": heal_id, "file": file, "from": old, "to": new, "test": test, "pr_url": url, "opened_at": float(opened),
            "repo": repo, "run_id": run_id,
            "runs": runs if isinstance(runs, int) and 0 <= runs <= 1_000_000 else 0, "failed_again": raw.get("failed_again") is True,
            "state": _text(raw.get("state"), 30), "done": raw.get("done") is True,
            "done_at": raw.get("done_at") if isinstance(raw.get("done_at"), (int, float)) else None}


def load(root: Path, env: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    try:
        data = json.loads(heals_path(root, env).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return []
    rows = data.get("heals") if isinstance(data, dict) else None
    return [e for e in (_entry(r, env) for r in (rows if isinstance(rows, list) else [])[:MAX_ENTRIES * 2]) if e][:MAX_ENTRIES]


def save(root: Path, entries: List[Dict[str, Any]], env: Optional[Dict[str, str]] = None, now: Optional[float] = None) -> Path:
    """Write the entries atomically (temp file, then rename), dropping finished ones older than 60 days."""
    now = time.time() if now is None else now
    keep = [e for e in entries if not (e["done"] and now - (e.get("done_at") or now) > KEEP_FINISHED_DAYS * DAY)][-MAX_ENTRIES:]
    path = heals_path(root, env)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".heals-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "heals": keep}, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def record_heals(root: Path, healed: List[Dict[str, Any]], pr_url: str, now: Optional[float] = None,
                 env: Optional[Dict[str, str]] = None, run_id: str = "") -> int:
    """Record the healed decisions of a run that raised `pr_url`. Each needs a heal id, a file, `from`, `to` and a test; a
    decision without one (a repeat served by the same fix) is not recorded. Returns how many were recorded."""
    if not is_pr_url(pr_url, env):
        return 0
    now = time.time() if now is None else now
    repo = (env if env is not None else os.environ).get("HEAL_REPO", "")[:200]
    entries = load(root, env)
    known = {e["heal_id"] for e in entries}
    added = 0
    for d in healed:
        raw = {"heal_id": d.get("heal_id"), "file": d.get("file"), "from": d.get("from"), "to": d.get("to"),
               "test": d.get("test"), "pr_url": pr_url, "opened_at": now, "repo": repo, "run_id": run_id}
        entry = _entry(raw, env)
        if entry and entry["heal_id"] not in known:
            entries.append(entry)
            known.add(entry["heal_id"])
            added += 1
    if added:
        heal_dir(root, env).mkdir(parents=True, exist_ok=True)
        save(root, entries, env, now)
    return added


def pr_url_from(output: str, env: Optional[Dict[str, str]] = None) -> str:
    """The pull request URL `gh pr create` printed (its last line that is one, on the pinned host), or ''."""
    for line in reversed((output or "").strip().splitlines()):
        if is_pr_url(line.strip(), env):
            return line.strip()
    return ""


# ---- what became of the heal --------------------------------------------------------------------------------------------
def gh_state(pr_url: str, run: Callable[..., Any] = subprocess.run, env: Optional[Dict[str, str]] = None) -> Optional[str]:
    """`open`, `closed_unmerged` or `merged` for the PR, or None when `gh` cannot say (missing, not signed in, offline). Only
    an address on the pinned host (github.com, or HEAL_GH_HOST) is ever handed to `gh`."""
    if not is_pr_url(pr_url, env):
        return None
    try:
        proc = run(["gh", "pr", "view", pr_url, "--json", "state"], capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return None
        return GH_STATES.get(str(json.loads(proc.stdout).get("state", "")).upper())
    except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
        return None


def line_state(root: Path, entry: Dict[str, Any], roots: Any) -> Optional[str]:
    """For a merged PR: `merged_unchanged` when the file still holds `to`, `reverted` when it is back to `from`, `edited` when
    it holds neither. None when the file cannot be read (outside the source roots, missing, not UTF-8)."""
    if not within_roots(root, entry["file"], roots):
        return None
    got = read_text_file(root, entry["file"])
    if got is None:
        return None
    text = got[0]
    if entry["to"] in text:
        return "merged_unchanged"
    return "reverted" if entry["from"] in text else "edited"


def _follow_one(root: Path, service: Any, e: Dict[str, Any], ran: Dict[Any, bool], roots: Any, now: float,
                gh: Callable[[str], Optional[str]]) -> Optional[Dict[str, Any]]:
    """Count this run for one entry, and send its follow-up when its PR state is known. The report that was sent, or None."""
    if e["test"] in ran:
        e["runs"] += 1
        e["failed_again"] = e["failed_again"] or ran[e["test"]]
    days = max(0, int((now - e["opened_at"]) // DAY))
    state = gh(e["pr_url"])
    if state == "merged":
        state = line_state(root, e, roots)
    if state is None:
        return None                                          # cannot know: skip, the counts are kept for next time
    report = {"pr_state": state, "failed_again": e["failed_again"], "runs_since": e["runs"], "days_since": days}
    body = {**report, "repo": e["repo"], **({"run_id": e["run_id"]} if e["run_id"] else {})}
    try:
        service.followup(e["heal_id"], body)
    except HealServiceError as err:
        if " 404" in str(err):                               # the service no longer holds the heal (retention): finished
            e["done"], e["done_at"] = True, now
        return None
    e["state"] = state
    if state in ("closed_unmerged", "reverted") or (e["runs"] >= DURABLE_RUNS and days >= DURABLE_DAYS):
        e["done"], e["done_at"] = True, now
    return report


def follow_up(root: Path, service: Any, cases: List[Dict[str, Any]], now: Optional[float] = None,
              gh: Optional[Callable[[str], Optional[str]]] = None, env: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """One follow-up per recorded heal that is not finished, sent to the service when its PR state is known. `cases` are the
    test cases of the run just made ({name, outcome}); `gh(pr_url)` gives open / closed_unmerged / merged. Returns what was
    sent, one dict per heal: {heal_id, test, pr_state, failed_again, runs_since, days_since}."""
    now = time.time() if now is None else now
    env = env if env is not None else os.environ
    gh = gh or (lambda url: gh_state(url, env=env))
    roots = source_roots(env)
    entries = load(root, env)
    sent: List[Dict[str, Any]] = []
    ran = {}
    for c in cases:
        if c.get("outcome") in ("passed", "failed"):
            ran[c.get("name")] = ran.get(c.get("name"), False) or c["outcome"] == "failed"
    for e in entries:
        if e["done"]:
            continue
        try:
            report = _follow_one(root, service, e, ran, roots, now, gh)
        except Exception:                                    # one bad entry never stops the others
            continue
        if report is not None:
            sent.append({"heal_id": e["heal_id"], "test": e["test"], **report})
    if entries:
        save(root, entries, env, now)
    return sent


__all__ = ["record_heals", "follow_up", "load", "save", "heals_path", "pr_url_from", "gh_state", "line_state"]
