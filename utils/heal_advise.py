"""
===============================================================================
In-Run Heal Advice (a failing test asks the heal service what the locator should be)
===============================================================================
When a test fails for good (after its reruns) with a locator error, the framework can ask the heal service, while the failing
page is still open, which element the broken step meant and how it should be written. The service answers in `advise` mode:
a decision and the best locator, never a patch. The decision goes into the healing report next to the test's other artifacts
and into `heal-summary.json`, and nothing in the repository is edited. This replaces the earlier direct-to-model path
(`utils/ai_healing.py`, deprecated): this module knows HTTP, the open page and the report, and nothing about models. No model
URL, name, prompt or reply parsing lives in this repository; the service owns all of that.

What it does for one failure:
    - reads the stack files under the source roots from the failure text, as the heal client does
    - runs the vendored probe on the live failing page (utils/heal_probe.js, the same script `scripts/heal.py` runs) and takes
      the page's aria snapshot; typed values never leave (the probe does not read them, the aria snapshot is redacted and the
      inventory is cut to an allowlist of keys here, whatever the service promises)
    - sends the last green run's fingerprint of the failing line when one was recorded (HEAL_FINGERPRINTS)
    - posts it to the service in advise mode (utils/heal_client.py builds the request) and writes the answer as a markdown
      report in the existing healing report folder plus a line of `heal-summary.json`

Features:
    ✓ Off unless HEAL_ADVISE=on AND HEAL_SERVICE_URL is set; never active inside `scripts/heal.py` (HEAL_RUN is set there)
    ✓ Never raises into a test: a service, browser or disk error is a `service_error` / `client_error` decision with the reason
    ✓ Every string from the service is untrusted: control characters are removed, one-line fields stay on one line, lengths are
      capped, and the locator is shown in a code fence longer than any backtick run inside it. The advised locator is text for a
      person to read: this module never evaluates it and never writes it to a source file
    ✓ AdviseRun keeps one decision per test and writes `heal-summary.json` (counts, token total, every decision, mode advise)
    ✓ The decision of a test is available by node id, so the observability report can carry the heal fields

Environment Variables:
    HEAL_ADVISE: "on" to ask the service for advice on a final locator failure (default off)
    HEAL_SERVICE_URL, HEAL_SERVICE_TOKEN: the service (see utils/heal_client.py)
    HEAL_SOURCE_ROOTS, HEAL_TEST_ID_ATTRIBUTE: as for `scripts/heal.py`
    HEAL_ARTIFACTS_DIR: where heal-summary.json goes (default test_artifacts)
    HEAL_RUN: set by scripts/heal.py while it runs the suite; no advice is asked then

Author: PMAC
===============================================================================
"""
import json
import os
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from config.artifact_paths import AI_HEALING_REPORT_DIR
from utils.heal_client import (EDITABLE_TEXTS_JS, HealServiceError, HealSettings, build_request, collect_source, last_pass_of,
                               run_total, stack_from_error, vendored_probe)
from utils.heal_redact import clean_inventory, redact_typed_values, scrub_texts

_ON = {"on", "1", "true", "yes"}
_STATUS = {"advised": "advised", "needs_human": "needs_human", "not_drift": "not_drift"}
ADVICE_KEYS = ("code", "strategy", "tier", "tier_movement", "below_floor", "why", "alternatives", "target_ref")


@dataclass
class AdviseSettings:
    """Whether in-run advice is on, and the heal client settings it uses."""
    enabled: bool
    heal: HealSettings

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "AdviseSettings":
        env = env if env is not None else os.environ
        heal = HealSettings.from_env(env)
        wanted = env.get("HEAL_ADVISE", "").strip().lower() in _ON
        return cls(enabled=wanted and bool(heal.url) and not env.get("HEAL_RUN"), heal=heal)


def find_page_object(item: Any) -> Any:
    """The Playwright page of a pytest item (a `page` fixture, an `app` with a page, a `*_page` fixture or a context)."""
    for name, value in (getattr(item, "funcargs", {}) or {}).items():
        if name == "page" and hasattr(value, "screenshot"):
            return value
        if name == "app" and hasattr(value, "page"):
            return value.page
        if name.endswith("_page") and hasattr(value, "screenshot"):
            return value
        if hasattr(value, "pages") and value.pages:
            return value.pages[0]
    return None


# ---- the page --------------------------------------------------------------------------------------------------------
async def snapshot_page(page: Any, probe: Optional[str] = None) -> Dict[str, Any]:
    """The live failing page as the heal request carries it: path, language signals, numbered inventory (allowlisted keys
    only), aria snapshot with typed text removed, viewport. The same shape `LivePage.snapshot()` returns."""
    data = await page.evaluate(probe or vendored_probe())
    meta = data.get("page") or {}
    inventory = clean_inventory([{**item, "ref": f"e{i}"} for i, item in enumerate(data.get("items") or [])
                                 if isinstance(item, dict)])
    try:
        editable = await page.evaluate(EDITABLE_TEXTS_JS)        # read only to be cut out of the snapshot, never sent
        aria = scrub_texts(redact_typed_values(await page.locator("body").aria_snapshot()), editable)
    except Exception:
        aria = None
    view = meta.get("viewport") or {}
    return {"path": urlsplit(page.url).path or "/", "inventory": inventory, "more": int(data.get("more") or 0), "aria": aria,
            "viewport": {"w": view.get("width"), "h": view.get("height"), "dpr": meta.get("dpr")},
            "language": {"html_lang": meta.get("lang") or None, "browser_locale": meta.get("browser_lang") or None,
                         "content_language": None}}


# ---- the service's answer --------------------------------------------------------------------------------------------
def _clean(value: Any, limit: int = 600, one_line: bool = True) -> str:
    """Untrusted text as safe text: control characters (and bidi and line separators) removed or turned into a space,
    capped. One line unless `one_line` is False (then newlines survive)."""
    text = str(value if value is not None else "")
    keep = "" if one_line else "\n"
    out = "".join(c if (c in keep or unicodedata.category(c) not in {"Cc", "Cf", "Cs", "Zl", "Zp"}) else " " for c in text)
    return (" ".join(out.split()) if one_line else out)[:limit]


def decision_of(resp: Dict[str, Any], test: str) -> Dict[str, Any]:
    """One decision record from the service's response: outcome (advised, needs_human, not_drift), reason, why, the advice
    (code, strategy, tier, tier movement, alternatives) and the usage. Every string is cleaned."""
    usage = resp.get("usage") if isinstance(resp.get("usage"), dict) else {}
    outcome = _STATUS.get(resp.get("status"), "needs_human")
    out: Dict[str, Any] = {
        "test": _clean(test, 500), "mode": "advise", "outcome": outcome, "heal_id": _clean(resp.get("heal_id"), 64) or None,
        "reason": _clean(resp.get("reason"), 80) or None, "why": _clean(resp.get("why")) or None,
        "settled_at": resp.get("settled_at") if isinstance(resp.get("settled_at"), int) else None,
        "usage": {k: int(usage.get(k, 0) or 0) if isinstance(usage.get(k, 0), (int, float)) else 0
                  for k in ("calls", "input_tokens", "output_tokens", "images")}}
    advice = resp.get("advice")
    if outcome == "advised" and isinstance(advice, dict):
        out["advice"] = {
            "code": _clean(advice.get("code"), 1000), "strategy": _clean(advice.get("strategy"), 40),
            "tier": _clean(advice.get("tier"), 40), "tier_movement": _clean(advice.get("tier_movement"), 10),
            "below_floor": bool(advice.get("below_floor")), "why": _clean(advice.get("why")),
            "target_ref": _clean(advice.get("target_ref"), 20),
            "alternatives": [_clean(a, 1000) for a in (advice.get("alternatives") or [])[:5] if isinstance(a, str)]}
    elif outcome == "advised":
        out["outcome"], out["reason"], out["why"] = "needs_human", "unusable_reply", "the service answered advised with no advice"
    return out


def error_decision(test: str, reason: str, why: str) -> Dict[str, Any]:
    return {"test": _clean(test, 500), "mode": "advise", "outcome": "needs_human", "heal_id": None, "reason": reason,
            "why": _clean(why, 300), "settled_at": None, "usage": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "images": 0}}


def advise(service: Any, settings: HealSettings, root: Path, failure: Dict[str, Any], snapshot: Dict[str, Any],
           run_id: Optional[str] = None) -> Dict[str, Any]:
    """Ask the service for advice on one failure (`failure`: name, classname, error; `snapshot`: snapshot_page()). Returns a
    decision; a service or request error is a needs_human decision with the reason, never an exception."""
    name = failure.get("name", "")
    try:
        stack = stack_from_error(failure.get("error", ""), settings.roots, root)
        files = collect_source(stack, settings.roots, root)
        last_pass = last_pass_of(root, stack)
        if last_pass:
            last_pass.pop("_page", None)
        request = build_request(failure, files, stack, snapshot, settings, root, last_pass, run_id, mode="advise")
        return decision_of(service.heal(request), name)
    except HealServiceError as e:
        return error_decision(name, "service_error", str(e))
    except Exception as e:                                  # a request that cannot be built, a disk error: no advice, no crash
        return error_decision(name, "client_error", f"the advise client failed ({type(e).__name__}): {str(e)[:200]}")


def metric_fields(decision: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The heal fields of a TestMetric (utils/test_observability.py) for a test's decision; empty when none was asked."""
    if not decision:
        return {}
    advice = decision.get("advice") or {}
    usage = decision.get("usage") or {}
    return {"heal_event": decision["outcome"] == "advised", "heal_outcome": decision["outcome"],
            "heal_id": decision.get("heal_id"), "heal_strategy": advice.get("strategy") or None,
            "heal_tier_movement": advice.get("tier_movement") or None, "heal_calls": usage.get("calls", 0),
            "heal_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)}


# ---- the report ------------------------------------------------------------------------------------------------------
def _fence(text: str) -> str:
    """`text` in a code fence longer than any backtick run inside it."""
    runs = re.findall(r"`+", text)
    fence = "`" * max(3, max((len(r) for r in runs), default=0) + 1)
    return f"{fence}\n{text}\n{fence}"


def _span(text: Any) -> str:
    """Untrusted text as an inline code span: its fence is longer than any backtick run inside it, so it cannot close the span,
    start a link, a heading or a mention."""
    text = _clean(text, 1000)
    runs = re.findall(r"`+", text)
    fence = "`" * (max((len(r) for r in runs), default=0) + 1)
    return f"{fence} {text} {fence}" if text else "``"


def report_text(decision: Dict[str, Any], context: Dict[str, Any]) -> str:
    """The markdown report of one decision. `context` holds test_name, url (path only), error_message and the timestamp."""
    adv = decision.get("advice") or {}
    lines = [
        "# Heal Service Advice Report", "",
        "## Test Information",
        f"- **Test Name**: {_span(context.get('test_name'))}",
        f"- **Timestamp**: {_span(context.get('timestamp', ''))}",
        f"- **Page Path**: {_span(context.get('path'))}",
        f"- **Heal Id**: {_span(decision.get('heal_id') or 'none')}", "",
        "## Error Details", _fence(_clean(context.get("error_message"), 2000, one_line=False)), "",
        "## Decision", f"- **Outcome**: {_span(decision['outcome'])}"]
    if decision.get("reason"):
        lines.append(f"- **Reason**: {_span(decision['reason'])}")
    if decision.get("why"):
        lines.append(f"- **Why**: {_span(decision['why'])}")
    if adv:
        lines += ["", "## Advised Locator", _fence(adv["code"]), f"- **Strategy**: {_span(adv['strategy'])}",
                  f"- **Tier**: {_span(adv['tier'])} ({_span(adv['tier_movement'])} from the broken locator)" +
                  (", below the broken locator's tier because nothing higher is unique" if adv["below_floor"] else ""),
                  f"- **Why**: {_span(adv['why'])}",
                  "- **Checked against the live page**: no. Check count 1 and the right element before using it."]
        if adv["alternatives"]:
            lines += ["", "### Other locators for the same element"] + [_fence(a) for a in adv["alternatives"]]
    u = decision["usage"]
    lines += ["", "## Usage", f"{u['calls']} model call(s), {u['input_tokens']} input / {u['output_tokens']} output tokens, "
              f"settled at step {_span(decision.get('settled_at') or 'n/a')}", "",
              "---", "*Advice only: nothing in the repository was edited. Generated by the heal service.*", ""]
    return "\n".join(lines)


def write_report(decision: Dict[str, Any], context: Dict[str, Any], directory: Optional[Path] = None) -> Path:
    """Write the markdown report into the healing report folder (the one the earlier AI healing reports used)."""
    directory = Path(directory or AI_HEALING_REPORT_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(context.get("test_name") or "test"))[:100]
    path = directory / f"{safe}_{stamp}_heal_advice.md"
    path.write_text(report_text(decision, {**context, "timestamp": stamp}), encoding="utf-8")
    return path


# ---- the run ---------------------------------------------------------------------------------------------------------
class AdviseRun:
    """The decisions of one pytest session, one per test (a later one for the same test replaces the earlier)."""

    def __init__(self) -> None:
        self.decisions: Dict[str, Dict[str, Any]] = {}
        self.run_id = uuid.uuid4().hex[:12]
        self.started = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    def add(self, nodeid: str, decision: Dict[str, Any]) -> None:
        self.decisions[nodeid] = decision

    def get(self, nodeid: str) -> Optional[Dict[str, Any]]:
        return self.decisions.get(nodeid)

    def summary(self) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = list(self.decisions.values())
        return {"run_id": self.run_id, "mode": "advise", "started": self.started,
                "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "failures": len(rows),
                "counts": {k: sum(1 for d in rows if d["outcome"] == k) for k in ("advised", "needs_human", "not_drift")},
                "usage": run_total(rows), "decisions": rows}

    def write_summary(self, directory: Optional[Path] = None) -> Optional[Path]:
        """Write heal-summary.json into the test artifacts folder (atomic); None when nothing was asked."""
        if not self.decisions:
            return None
        directory = Path(directory or os.getenv("HEAL_ARTIFACTS_DIR", "test_artifacts"))
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "heal-summary.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.summary(), indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return path

    def print_decision(self, decision: Dict[str, Any]) -> None:
        u = decision["usage"]
        tokens = f"tokens {u['input_tokens']} in / {u['output_tokens']} out, {u['calls']} call(s)"
        if decision["outcome"] == "advised":
            adv = decision["advice"]
            print(f"[heal advise] {decision['test']}: {adv['code']}  ({adv['tier_movement']}, {adv['strategy']}; {tokens})")
        else:
            reason = f" [{decision['reason']}]" if decision.get("reason") else ""
            print(f"[heal advise] {decision['outcome']}{reason} {decision['test']}: {decision.get('why')}  ({tokens})")


__all__ = ["AdviseSettings", "AdviseRun", "advise", "decision_of", "error_decision", "find_page_object", "report_text",
           "metric_fields", "snapshot_page", "write_report"]
