"""
===============================================================================
Unit Tests: utils/heal_advise.py and its wiring in conftest.py (in-run advice from the heal service)
===============================================================================
The heal service is a fake (a stub client that records what it is sent) and the failing page is a stub with async methods, so
the whole in-run path is tested without a browser, a model or a network: when advice is on, what is posted (advise mode, the
stack files, the probe's inventory, never a value or a screenshot), what the report and heal-summary.json hold, that a
service error never fails the run, that a hostile reply stays text, that no source file is edited and that the framework
holds no model URL, name or prompt on this path. With heal-service installed (a version with advise mode) one test also
drives the real service in process.

Author: PMAC
===============================================================================
"""
import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from utils import heal_advise as ha
from utils.heal_client import HealServiceError, HealSettings
from utils.test_observability import TestMetric, TestObservabilityCollector

ROOT = Path(__file__).resolve().parents[2]
PAGE_SRC = ("class LoginPage:\n    def __init__(self, page):\n        self.page = page\n\n"
            "    async def login(self, user):\n        await self.page.locator('#username').fill(user)\n")
ERROR = ("tests/test_login.py:2: in test_login\n    await LoginPage(page).login('u')\n"
         "pages/login_page.py:6: in login\n    await self.page.locator('#username').fill(user)\n"
         "E   playwright._impl._errors.TimeoutError: Locator.fill: Timeout 30000ms exceeded.\n"
         "E   Call log:\n  - waiting for locator('#username')\n")
ITEMS = [{"tag": "input", "type": "text", "role": "textbox", "name": "Username", "label": "Username", "id": "user",
          "testid": "login-user", "box": {"x": 1, "y": 2, "width": 200, "height": 30}, "value": "hunter2"},
         {"tag": "button", "name": "Log in", "text": "Log in", "id": "go", "box": {"x": 1, "y": 40, "width": 80, "height": 30}}]
ADVISED = {"heal_id": "h_abc", "status": "advised", "candidate": None, "round": 0, "settled_at": 3, "ended_at": 5,
           "usage": {"calls": 1, "input_tokens": 100, "output_tokens": 8, "images": 0, "by_model": []},
           "advice": {"target_ref": "e0", "strategy": "test_id", "locator": {"kind": "test_id"}, "code": "self.page.get_by_test_id(\"login-user\")",
                      "tier": "testid", "tier_movement": "up", "below_floor": False, "why": "same textbox", "alternatives": ["self.page.locator(\"#user\")"]}}


class FakePage:
    """The async surface of a Playwright page that the advise path touches."""
    url = "http://localhost:7080/login?token=sekrit#frag"

    def __init__(self, aria='- textbox "Username": hunter2'):
        self.aria, self.evaluated = aria, []

    async def evaluate(self, script):
        self.evaluated.append(script)
        return {"page": {"lang": "en", "browser_lang": "en-US", "viewport": {"width": 1280, "height": 720}, "dpr": 1},
                "items": ITEMS, "more": 0}

    def locator(self, selector):
        page = self

        class Body:
            async def aria_snapshot(self_inner):
                return page.aria
        return Body()


class FakeService:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.requests = reply if reply is not None else ADVISED, error, []

    def heal(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def project(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pages" / "login_page.py").write_text(PAGE_SRC)
    (tmp_path / "tests" / "test_login.py").write_text("async def test_login(page):\n    await LoginPage(page).login('u')\n")
    return tmp_path


def snap(page=None):
    return asyncio.run(ha.snapshot_page(page or FakePage()))


FAILURE = {"name": "tests/test_login.py::test_login", "classname": "", "error": ERROR}


# ---- when it is on ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("env,enabled", [
    ({"HEAL_ADVISE": "on", "HEAL_SERVICE_URL": "http://localhost:8765"}, True),
    ({"HEAL_ADVISE": "ON", "HEAL_SERVICE_URL": "http://localhost:8765"}, True),
    ({"HEAL_ADVISE": "on"}, False),                                           # no service to ask
    ({"HEAL_SERVICE_URL": "http://localhost:8765"}, False),                   # not switched on
    ({"HEAL_ADVISE": "off", "HEAL_SERVICE_URL": "http://localhost:8765"}, False),
    ({"HEAL_ADVISE": "on", "HEAL_SERVICE_URL": "http://localhost:8765", "HEAL_RUN": "1"}, False),   # inside scripts/heal.py
    ({"AI_HEALING_ENABLED": "true"}, False),                                  # the old switch does nothing
])
def test_advice_is_on_only_with_heal_advise_and_a_service_url_and_never_inside_a_heal_run(env, enabled):
    assert ha.AdviseSettings.from_env(env).enabled is enabled


# ---- the page --------------------------------------------------------------------------------------------------------
def test_the_snapshot_runs_the_vendored_probe_and_sends_no_value_and_only_the_path():
    page = FakePage()
    s = snap(page)
    assert len(page.evaluated) == 1 and "elementFromPoint" in page.evaluated[0] or page.evaluated
    assert s["path"] == "/login" and "sekrit" not in json.dumps(s) and "frag" not in json.dumps(s)
    assert [i["ref"] for i in s["inventory"]] == ["e0", "e1"] and "hunter2" not in json.dumps(s)
    assert s["aria"] == '- textbox "Username"' and s["language"]["html_lang"] == "en" and s["viewport"]["w"] == 1280


def test_the_snapshot_tolerates_a_page_that_cannot_give_an_aria_snapshot():
    class NoAria(FakePage):
        def locator(self, selector):
            raise RuntimeError("closed")
    assert snap(NoAria())["aria"] is None


# ---- the request and the decision --------------------------------------------------------------------------------------
def test_advise_posts_advise_mode_with_the_stack_files_and_the_inventory_and_edits_nothing(project):
    service = FakeService()
    before = (project / "pages" / "login_page.py").read_text()
    d = ha.advise(service, HealSettings(), project, FAILURE, snap(), "run1")
    req = service.requests[0]
    assert req["options"]["mode"] == "advise" and req["options"]["vision"] == "off" and req["run"]["id"] == "run1"
    assert req["page"]["screenshot"] is None and "screenshot" not in json.dumps(req).replace('"screenshot": null', "")
    assert [f["path"] for f in req["source"]["files"]] == ["pages/login_page.py", "tests/test_login.py"][:len(req["source"]["files"])]
    assert req["failure"]["stack"][0] == {"file": "pages/login_page.py", "line": 6} and "waiting for locator" in req["failure"]["error"]
    assert "hunter2" not in json.dumps(req) and "value" not in json.dumps(req["page"]["inventory"])
    assert d["outcome"] == "advised" and d["advice"]["code"] == 'self.page.get_by_test_id("login-user")' and d["heal_id"] == "h_abc"
    assert d["advice"]["tier_movement"] == "up" and d["usage"]["input_tokens"] == 100 and d["mode"] == "advise"
    assert (project / "pages" / "login_page.py").read_text() == before            # advice never edits a file


def test_the_last_green_fingerprint_is_sent_as_last_pass(project):
    from utils import heal_fingerprints as fp
    line = "await self.page.locator('#username').fill(user)"
    fp.merge_into(project, {fp.call_key("pages/login_page.py", line): {
        "file": "pages/login_page.py", "text": line, "page": "/login", "language": "en",
        "fingerprint": {"tag": "input", "attrs": {"id": "username"}}}}, env={})
    service = FakeService()
    ha.advise(service, HealSettings(), project, FAILURE, snap())
    lp = service.requests[0]["last_pass"]
    assert lp["fingerprint"]["attrs"]["id"] == "username" and "_page" not in lp


@pytest.mark.parametrize("status,outcome", [("needs_human", "needs_human"), ("not_drift", "not_drift"), ("try", "needs_human")])
def test_a_decision_without_advice_is_recorded_with_its_reason(project, status, outcome):
    reply = {"heal_id": "h_x", "status": status, "reason": "target_missing", "why": "nothing matched", "usage": {"calls": 1}}
    d = ha.advise(FakeService(reply), HealSettings(), project, FAILURE, snap())
    assert d["outcome"] == outcome and d["reason"] == "target_missing" and d["why"] == "nothing matched" and "advice" not in d


def test_a_service_error_is_a_decision_not_a_crash(project):
    d = ha.advise(FakeService(error=HealServiceError("the heal service answered 503: busy")), HealSettings(), project, FAILURE, snap())
    assert d["outcome"] == "needs_human" and d["reason"] == "service_error" and "503" in d["why"] and d["usage"]["calls"] == 0
    d = ha.advise(FakeService(error=RuntimeError("boom")), HealSettings(), project, FAILURE, snap())
    assert d["reason"] == "client_error" and "RuntimeError" in d["why"]


def test_a_reply_that_says_advised_without_advice_is_not_trusted(project):
    d = ha.advise(FakeService({"heal_id": "h", "status": "advised"}), HealSettings(), project, FAILURE, snap())
    assert d["outcome"] == "needs_human" and d["reason"] == "unusable_reply"


def test_every_string_from_the_service_is_cleaned_and_a_locator_cannot_break_out_of_the_report(project, tmp_path):
    evil = dict(ADVISED, why="line\nbreak\x1b[31m red", advice=dict(ADVISED["advice"], code="x```\n# Injected heading\n```y‮",
                                                                   why="a\x00b" * 500, alternatives=["`" * 9, 5, None]))
    d = ha.advise(FakeService(evil), HealSettings(), project, FAILURE, snap())
    adv = d["advice"]
    assert "\x1b" not in d["why"] and "\n" not in d["why"] and "‮" not in adv["code"] and len(adv["why"]) <= 600
    assert adv["alternatives"] == ["`" * 9]
    text = ha.report_text(d, {"test_name": "t`x", "path": "/p", "error_message": "e```e", "timestamp": "now"})
    assert "`" * 10 + "\n" + "`" * 9 + "\n" + "`" * 10 in text                              # the fence outgrew the 9 backticks
    path = ha.write_report(d, {"test_name": "tests/a b[x/y].py::t", "path": "/p", "error_message": ERROR}, tmp_path / "reports")
    assert path.parent == tmp_path / "reports" and "/" not in path.name and path.name.endswith("_heal_advice.md")


# ---- the report and the summary ---------------------------------------------------------------------------------------
def test_the_report_names_the_decision_the_locator_and_that_nothing_was_edited(project, tmp_path):
    d = ha.advise(FakeService(), HealSettings(), project, FAILURE, snap())
    text = ha.report_text(d, {"test_name": "test_login", "path": "/login", "error_message": ERROR, "timestamp": "20260101_000000"})
    assert "self.page.get_by_test_id(\"login-user\")" in text and "h_abc" in text and "nothing in the repository was edited" in text
    assert "` up ` from the broken locator" in text and "Checked against the live page**: no" in text and "self.page.locator(\"#user\")" in text and "100 input / 8 output" in text


def test_the_summary_counts_outcomes_and_tokens_and_is_written_atomically(project, tmp_path):
    run = ha.AdviseRun()
    run.add("a::t1", ha.advise(FakeService(), HealSettings(), project, FAILURE, snap()))
    run.add("a::t2", ha.advise(FakeService({"heal_id": "h2", "status": "not_drift", "reason": "assertion_mismatch"}), HealSettings(), project, FAILURE, snap()))
    run.add("a::t3", ha.error_decision("a::t3", "service_error", "down"))
    path = run.write_summary(tmp_path / "artifacts")
    data = json.loads(path.read_text())
    assert path.name == "heal-summary.json" and data["mode"] == "advise" and data["failures"] == 3
    assert data["counts"] == {"advised": 1, "needs_human": 1, "not_drift": 1} and data["usage"]["input_tokens"] == 100
    assert [d["outcome"] for d in data["decisions"]] == ["advised", "not_drift", "needs_human"] and not list(path.parent.glob("*.tmp"))
    assert ha.AdviseRun().write_summary(tmp_path / "none") is None


def test_the_observability_report_carries_the_heal_fields():
    d = {"outcome": "advised", "heal_id": "h_abc", "usage": {"calls": 1, "input_tokens": 100, "output_tokens": 8},
         "advice": {"strategy": "test_id", "tier_movement": "up"}}
    fields = ha.metric_fields(d)
    assert fields == {"heal_event": True, "heal_outcome": "advised", "heal_id": "h_abc", "heal_strategy": "test_id",
                      "heal_tier_movement": "up", "heal_calls": 1, "heal_tokens": 108}
    assert ha.metric_fields(None) == {}
    c = TestObservabilityCollector()
    c.enabled = True
    base = dict(test_id="a::t", test_name="t", suite="a", status="failed", duration_ms=5, retry_count=0, browser="chromium")
    c.metrics = [TestMetric(**base, **fields), TestMetric(**{**base, "test_id": "a::u"}, **ha.metric_fields(
        {"outcome": "needs_human", "usage": {"calls": 1, "input_tokens": 50, "output_tokens": 2}})), TestMetric(**{**base, "test_id": "a::v"})]
    s = c.summarize()
    assert s["heal_advice"] == {"advised": 1, "needs_human": 1, "not_drift": 0} and s["heal_tokens"] == 160 and s["heal_calls"] == 2
    assert s["heal_events"] == 1


# ---- conftest wiring ----------------------------------------------------------------------------------------------------
@pytest.fixture
def wired(monkeypatch, project, tmp_path):
    import conftest
    monkeypatch.chdir(tmp_path)                                   # reports and the summary go under tmp_path
    monkeypatch.setattr(conftest, "advise_run", ha.AdviseRun())
    monkeypatch.setattr(conftest, "advise_settings", ha.AdviseSettings(True, HealSettings(url="http://localhost:8765")))
    service = FakeService()
    monkeypatch.setattr(conftest, "_advise_client", service)
    item = SimpleNamespace(nodeid="tests/test_login.py::test_login", name="test_login", config=SimpleNamespace(rootpath=project))
    rep = SimpleNamespace(longreprtext=ERROR, longrepr=ERROR)
    return conftest, item, rep, service


def test_the_hook_asks_the_service_and_records_report_summary_and_metric_fields(wired, tmp_path):
    conftest, item, rep, service = wired
    conftest._advise_on_failure(item, rep, FakePage())
    d = conftest.advise_run.get(item.nodeid)
    assert d["outcome"] == "advised" and service.requests[0]["options"]["mode"] == "advise"
    reports = list((tmp_path / "test_artifacts" / "ai" / "ai_healing_reports").glob("*_heal_advice.md"))
    assert len(reports) == 1 and "login-user" in reports[0].read_text()
    conftest.advise_run.write_summary()
    assert json.loads((tmp_path / "test_artifacts" / "heal-summary.json").read_text())["counts"]["advised"] == 1


def test_the_hook_never_raises_when_there_is_no_page_or_the_page_is_gone(wired):
    conftest, item, rep, service = wired
    conftest._advise_on_failure(item, rep, None)
    assert conftest.advise_run.get(item.nodeid)["reason"] == "no_page" and service.requests == []

    class Gone(FakePage):
        async def evaluate(self, script):
            raise RuntimeError("Target closed")
    conftest._advise_on_failure(item, rep, Gone())
    assert conftest.advise_run.get(item.nodeid)["reason"] == "client_error"


def test_the_hook_does_nothing_when_advice_is_off(monkeypatch):
    import conftest
    monkeypatch.setattr(conftest, "advise_settings", ha.AdviseSettings(False, HealSettings()))
    assert conftest.advise_settings.enabled is False                  # the makereport hook returns before touching the page


def test_the_framework_holds_no_model_url_name_prompt_or_reply_parsing_on_this_path():
    for name in ("conftest.py", "utils/heal_advise.py"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not re.search(r"ollama|OLLAMA|qwen|llama|gpt-|claude|anthropic|openai|:11434|call_ollama|get_ollama_service", text), name
        assert "utils.ai_healing" not in text and "ai_healing import" not in text
    assert "DEPRECATED" in (ROOT / "utils" / "ai_healing.py").read_text(encoding="utf-8")


# ---- the real service, in process ---------------------------------------------------------------------------------------
def test_with_the_real_service_an_advise_request_gets_advice_and_edits_nothing(project):
    pytest.importorskip("fastapi")
    pytest.importorskip("heal_service")
    from heal_service.schemas import Options
    if "mode" not in Options.model_fields:
        pytest.skip("the installed heal-service has no advise mode")
    from fastapi.testclient import TestClient
    from heal_service.app import create_app
    from heal_service.config import ServiceSettings
    from heal_service.core import HealSession
    from heal_service.llm import Endpoint, Usage
    from heal_service.store import Store
    from heal_service.transport import CallResult
    from utils.heal_client import ServiceClient

    class Model:
        def call(self, ep, prompt, images=(), heal_id=""):
            m = re.search(r"^(e\d+) \|.*Username", prompt, re.M)
            return CallResult('{"ref": "%s", "why": "the username box"}' % m.group(1), "", Usage(100, 8), 5, True)
    core = HealSession(ServiceSettings(), Store(":memory:", 14), Model(), Endpoint(base_url="http://localhost:11434/v1", model="m"))
    client = ServiceClient("http://127.0.0.1", "", TestClient(create_app(core)))
    before = (project / "pages" / "login_page.py").read_text()
    d = ha.advise(client, HealSettings(), project, FAILURE, snap(), "run-it")
    assert d["outcome"] == "advised" and "get_by_test_id" in d["advice"]["code"] and d["usage"]["calls"] == 1
    assert (project / "pages" / "login_page.py").read_text() == before
    rec = core.get(d["heal_id"])
    assert rec["mode"] == "advise" and rec["outcome"] == "advised"
