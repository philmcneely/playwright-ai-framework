"""
===============================================================================
Contract Replay: every heal-service fixture, through the Python client, against a fake service
===============================================================================
`tests/unit/fixtures/heal_contract/<case>/` holds a drifted page object and the service's recorded answer at each step of one
conversation (a copy of the service repository's contract fixtures, the same files the TypeScript client replays). The fake
service here answers from `expected.json`, rebuilding the patch (hash and span) from the request's own source files, and
`utils.heal_client.Healer` runs the whole loop against a temp project: it must check the same locator in the live page that
the fixture records, report the scripted result for every candidate, write the same locator into the file only when the
service says healed (and leave the file alone otherwise), and end with the same decision and reason.

Author: PMAC
===============================================================================
"""
import hashlib
import json
import re
from pathlib import Path

import pytest

from utils.heal_client import HELPER_IMPORT, Healer, HealSettings
from utils.heal_locale import page_language

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "heal_contract"
CASES = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir() and (p / "request.json").exists())
INTERNAL = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b[a-z0-9-]+\.(?:local|lan|internal|home|corp|ts\.net)\b", re.I)


def load(case, name):
    return json.loads((FIXTURES / case / name).read_text(encoding="utf-8"))


def locate(content, text, line=None):
    """Start offset of `text` in `content`: on `line` (1-based) when given and found there, else its first occurrence."""
    if line:
        start = sum(len(part) for part in content.splitlines(True)[:line - 1])
        at = content.find(text, start)
        if at >= 0:
            return at
    return content.index(text)


class FakeLive:
    """The live page: it answers a locator check with the scripted count and element, and remembers what it was asked."""

    def __init__(self, request, service):
        page = request["page"]
        self.service, self.checked, self.inventory = service, [], page.get("inventory", [])
        lang = page.get("language") or {}
        self.language = page_language(lang.get("html_lang"), lang.get("browser_locale"), lang.get("content_language"))
        self._snap = {"path": "/" + page["url"].split("/", 3)[-1], "inventory": page.get("inventory", []), "more": 0, "aria": None,
                      "viewport": {"w": 1280, "h": 720, "dpr": 1}, "language": lang}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def snapshot(self):
        return self._snap

    def check(self, expression):
        self.checked.append(expression)
        scripted = self.service.script["results"][self.service.reported]
        return scripted.get("count"), (scripted.get("hit") or {}).get("ref")


class FakeService:
    """Answers POST /v1/heal and /result from the fixture's expected steps, as the service's own responses would read."""

    def __init__(self, case, files, stack):
        self.script, self.steps = load(case, "script.json"), load(case, "expected.json")["python"]
        self.files, self.stack, self.reported, self.requests, self.reports = files, stack, 0, [], []

    def probe_js(self):
        return ""

    def _patch(self, p, first=False):
        content = self.files[p["file"]]
        line = self.stack[0]["line"] if first and p["file"] == self.stack[0]["file"] else None
        start = locate(content, p["from"], line)
        return {"file": p["file"], "base_sha256": hashlib.sha256(content.encode()).hexdigest(), "from": p["from"], "to": p["to"],
                "span": {"start": start, "end": start + len(p["from"])}, "diff": ""}

    def _response(self, i):
        step = self.steps[i]
        out = {"heal_id": "h_fixture", "status": step["status"], "round": step["round"], "reason": step["reason"],
               "why": None if step["status"] in ("try", "healed") else f"fixture: {step['reason']}",
               "usage": {**step["usage"], "images": 0, "by_model": []}, "cache_hit": step["cache_hit"],
               "settled_at": step["settled_at"], "ended_at": step["ended_at"]}
        cand = step.get("candidate")
        if cand:
            out["candidate"] = {**{k: cand[k] for k in ("target_ref", "strategy", "tier", "tier_movement", "below_floor", "locator",
                                                         "code", "branches", "expect")},
                                "patch": self._patch(cand["patch"], first=True),
                                "also_patches": [self._patch(p) for p in cand.get("also_patches") or []],
                                "why": "fixture", "model_note_untrusted": ""}
        return out

    def heal(self, request):
        self.requests.append(request)
        return self._response(0)

    def result(self, heal_id, report):
        self.reports.append(report)
        self.reported += 1
        assert self.reported <= len(self.script["results"]), "the client reported more results than the fixture scripts"
        return self._response(self.reported)


def replay(case, tmp_path):
    request = load(case, "request.json")
    assert request["client"]["language"] == "python"
    files = {f["path"]: f["content"] for f in request["source"]["files"]}
    for path, content in files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    stack = request["failure"]["stack"]
    error = "\n".join(f"{f['file']}:{f['line']}: in frame" for f in reversed(stack)) + "\n" + request["failure"]["error"]
    service = FakeService(case, files, stack)
    live = FakeLive(request, service)
    settings = HealSettings(url="http://localhost:8765", roots=tuple(request["source"].get("roots") or ("pages", "tests", "utils")),
                            test_id_attribute=request.get("test_id_attribute", "data-testid"), base_url="http://app.example")

    def verify(failure):
        return service.script["results"][service.reported].get("test_outcome") == "passed"
    healer = Healer(service, settings, verify, root=tmp_path, live_factory=lambda route, probe: live, run_id="contract")
    decision = healer.heal({"name": request["test"]["title"] or "t", "classname": "", "error": error})
    return request, files, service, live, decision


@pytest.mark.parametrize("case", CASES)
def test_the_client_reaches_the_fixtures_decision_and_checks_and_writes_the_recorded_locator(case, tmp_path):
    request, files, service, live, decision = replay(case, tmp_path)
    steps = service.steps
    last = steps[-1]
    # every step was consumed: the client reported once per `try` answer, no more and no less
    assert service.reported == len(steps) - 1
    # the decision
    want = {"healed": "healed", "not_drift": "not_drift", "needs_human": "needs_human"}[last["status"]]
    assert decision["outcome"] == want, decision
    if last["status"] == "needs_human":
        assert decision["reason"] == last["reason"]
    assert decision["usage"]["calls"] == last["usage"]["calls"] and decision["usage"]["input_tokens"] == last["usage"]["input_tokens"]
    # the locator the client checked live at each candidate is the one the fixture records for the page's language; a
    # candidate's extra patches are checked live only when its own locator matched the expected element
    tries = [s for s in steps if s["status"] == "try"]
    scripted = service.script["results"]
    at = 0
    for i, step in enumerate(tries):
        cand = step["candidate"]
        expression = cand["branches"][live.language] if cand["branches"] else cand["code"]
        assert live.checked[at] == expression, (i, live.checked)
        at += 1
        if scripted[i]["count"] == 1 and (scripted[i].get("hit") or {}).get("ref") == cand["expect"]["ref"]:
            at += len(cand.get("also_patches") or [])
    assert at == len(live.checked)
    # what the client reported for each candidate is what the script says it saw, and it re-ran the test only after an edit
    for report, result, step in zip(service.reports, scripted, tries):
        assert report["count"] == result["count"] and report.get("hit") == result.get("hit")
        edited = result["count"] == 1 and (result.get("hit") or {}).get("ref") == step["candidate"]["expect"]["ref"]
        if edited:
            assert report["test_outcome"] == result["test_outcome"]
        else:
            assert "test_outcome" not in report
    # the file: exactly the recorded locator when healed, untouched otherwise
    for path, original in files.items():
        now = (tmp_path / path).read_text(encoding="utf-8")
        patch = last["candidate"]["patch"] if last["status"] == "healed" else None
        if patch and path == patch["file"]:
            start = locate(original, patch["from"], service.stack[0]["line"])
            expected = original[:start] + patch["to"] + original[start + len(patch["from"]):]
            assert now.replace(HELPER_IMPORT + "\n", "", 1) == expected
            assert (HELPER_IMPORT in now) == ("by_language(" in patch["to"])
        else:
            assert now == original


@pytest.mark.parametrize("case", CASES)
def test_a_candidates_locator_chain_names_the_calls_its_code_makes(case):
    for step in load(case, "expected.json")["python"]:
        cand = step.get("candidate")
        if not cand or cand["branches"] or cand["locator"]["kind"] == "by_language":
            continue
        calls = re.findall(r"\.(\w+)\(", cand["code"].split("self.page", 1)[1])
        assert [s["m"] for s in cand["locator"]["chain"]] == calls
        assert cand["code"].startswith("self.page.")


def test_the_fixtures_cover_every_case_the_service_ships():
    assert len(CASES) == 13 and {"french_page_language_branch", "wrong_element_repick", "prompt_injection_in_page_text",
                                 "not_drift", "budget_exhausted"} <= set(CASES)


def test_the_fixtures_hold_no_internal_host_or_address():
    hits = [(p.relative_to(FIXTURES).as_posix(), m.group(0)) for p in FIXTURES.rglob("*") if p.is_file()
            for m in INTERNAL.finditer(p.read_text(encoding="utf-8"))]
    assert hits == []
    for p in FIXTURES.rglob("*.json"):
        for m in re.finditer(r"https?://([^/\s\"']+)", p.read_text(encoding="utf-8")):
            assert m.group(1).split(":")[0] in ("localhost", "app.example"), (p.name, m.group(0))
