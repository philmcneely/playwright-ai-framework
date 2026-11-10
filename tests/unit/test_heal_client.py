"""
===============================================================================
Unit Tests: utils/heal_client.py -- request building, patch safety, the try->result loop
===============================================================================
The heal service is a fake (httpx MockTransport with scripted answers) and the live page is a stub, so every decision the
client makes is tested without a browser, a model or a network: what it sends, which patches it refuses and why, that a
wrong count or element never edits a file, that a failed re-run reverts, and that a service error becomes a needs_human
decision instead of a crash.

Author: PMAC
===============================================================================
"""
import hashlib
import json

import httpx
import pytest

from utils import heal_fingerprints as fp
from utils.heal_redact import redact_failure_text
from utils.heal_client import (HealServiceError, HealSettings, Healer, ServiceClient, build_locator, check_replacement,
                               collect_source, match_ref, run_total, stack_from_error, junit_test_id)

PAGE_SRC = (
    "from playwright.async_api import Page\n"
    "\n"
    "\n"
    "class LoginPage:\n"
    "    def __init__(self, page):\n"
    "        self.page = page\n"
    '        self.url = f"{BASE_URL}/login"\n'
    "\n"
    "    async def login(self, user):\n"
    "        await self.page.locator('#username').fill(user)\n"
    "        await self.page.locator('#username').press('Tab')\n"
)
TEST_SRC = "async def test_valid_login(page):\n    await LoginPage(page).login('u')\n"
FROM = "self.page.locator('#username')"
TO = "self.page.get_by_test_id('login-user')"
ERROR = ("tests/test_login.py:2: in test_valid_login\n    await LoginPage(page).login('u')\n"
         "pages/login_page.py:10: in login\n    await self.page.locator('#username').fill(user)\n"
         "E   TimeoutError: waiting for locator('#username')\n")
FAILURE = {"name": "test_valid_login", "classname": "tests.test_login", "error": ERROR}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def project(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "VERSION").write_text("1.2.3\n")
    (tmp_path / "pages" / "login_page.py").write_text(PAGE_SRC)
    (tmp_path / "pages" / "other_page.py").write_text("x = self.page.locator('#username')\n")
    (tmp_path / "tests" / "test_login.py").write_text(TEST_SRC)
    return tmp_path


def patch_for(root, to=TO, frm=FROM, file="pages/login_page.py", nth=0, base=None):
    """A service patch for the `nth` occurrence of `frm` in `file`."""
    text = (root / file).read_text()
    start = -1
    for _ in range(nth + 1):
        start = text.index(frm, start + 1)
    return {"file": file, "base_sha256": base or sha(text), "span": {"start": start, "end": start + len(frm)},
            "from": frm, "to": to, "diff": ""}


def candidate(root, to=TO, ref="e0", branches=None, also=None, **patch_kw):
    return {"target_ref": ref, "strategy": "test_id", "locator": {"kind": "test_id"}, "code": to, "branches": branches,
            "expect": {"count": 1, "ref": ref}, "patch": patch_for(root, to, **patch_kw), "also_patches": also or [],
            "why": "same textbox", "tier": "testid", "tier_movement": "up", "below_floor": False}


def reply(status, cand=None, hid="h_1", rnd=1, **kw):
    return {"heal_id": hid, "status": status, "candidate": cand, "round": rnd, "settled_at": 2, "reason": kw.get("reason"),
            "why": kw.get("why"), "usage": kw.get("usage", {"calls": 1, "input_tokens": 100, "output_tokens": 9, "images": 0})}


class FakeService:
    """A scripted service: the first reply answers /v1/heal, the rest answer /result in order."""

    def __init__(self, *replies, status=200):
        self.replies, self.status, self.requests = list(replies), status, []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, path, body, request.headers.get("authorization")))
        if path == "/v1/probe.js":
            return httpx.Response(200, text="(only) => ({items: [], more: 0, page: {}})")
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "boom"})
        return httpx.Response(200, json=self.replies.pop(0) if self.replies else reply("needs_human", reason="x", why="no more scripted replies"))

    def client(self, token=""):
        return ServiceClient("https://svc", token, httpx.Client(transport=httpx.MockTransport(self.handler)))

    def posts(self, suffix):
        return [b for m, p, b, _ in self.requests if m == "POST" and p.endswith(suffix)]


class FakeLive:
    def __init__(self, checks=None, language="en", inventory=None):
        self.checks, self.language, self.inventory = checks or {}, language, inventory or [{"ref": "e0", "tag": "input"}]
        self.asked = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def snapshot(self):
        return {"path": "/login", "inventory": self.inventory, "more": 0, "aria": "- textbox \"Username\"",
                "viewport": {"w": 1280, "h": 720, "dpr": 1},
                "language": {"html_lang": self.language, "browser_locale": "en-US", "content_language": None}}

    def check(self, expression):
        self.asked.append(expression)
        return self.checks.get(expression, (1, "e0"))


class Verify:
    def __init__(self, *outcomes, root=None, file="pages/login_page.py"):
        self.outcomes, self.calls, self.root, self.file, self.seen = list(outcomes), 0, root, file, []

    def __call__(self, test):
        self.calls += 1
        self.seen.append((self.root / self.file).read_text())
        return self.outcomes.pop(0)


def healer(project, service, verify, live=None, **kw):
    live = live or FakeLive()
    h = Healer(service.client(), HealSettings(url="http://svc"), verify, root=project, run_id="r1",
               live_factory=lambda route, probe: live)
    h.live = live
    return h


# ---- request building --------------------------------------------------------------------------------------------------
class TestRequest:
    def test_sends_stack_files_under_roots_with_hash_and_the_page_evidence(self, project):
        svc = FakeService(reply("not_drift"))
        d = healer(project, svc, Verify()).heal(FAILURE)
        body = svc.posts("/v1/heal")[0]
        assert [f["path"] for f in body["source"]["files"]] == ["pages/login_page.py", "tests/test_login.py"]
        assert body["source"]["files"][0]["sha256"] == sha(PAGE_SRC) and body["source"]["files"][0]["content"] == PAGE_SRC
        assert body["source"]["roots"] == ["pages", "tests", "utils"]
        assert body["failure"]["stack"] == [{"file": "pages/login_page.py", "line": 10}, {"file": "tests/test_login.py", "line": 2}]
        assert body["test"] == {"id": "tests/test_login.py::test_valid_login", "title": "test_valid_login"}
        assert body["client"] == {"framework": "playwright-ai-framework", "language": "python", "version": "1.2.3"}
        assert body["page"]["language"]["html_lang"] == "en" and body["page"]["url"] == "/login"
        assert body["page"]["screenshot"] is None and body["options"]["vision"] == "off"
        assert body["test_id_attribute"] == "data-testid" and body["run"]["id"] == "r1"
        assert d["outcome"] == "not_drift"

    def test_never_carries_a_value_cookie_storage_or_image_key(self, project):
        svc = FakeService(reply("not_drift"))
        healer(project, svc, Verify()).heal(FAILURE)
        stack, bad = [svc.posts("/v1/heal")[0]], {"value", "cookie", "cookies", "storage", "storage_state", "png_base64"}
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                assert not bad & {k.lower() for k in node}
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)

    def test_token_is_sent_as_a_bearer_header(self, project):
        svc = FakeService(reply("not_drift"))
        h = Healer(svc.client("tok"), HealSettings(), Verify(), root=project, live_factory=lambda r, p: FakeLive())
        h.heal(FAILURE)
        assert {a for *_, a in svc.requests} == {"Bearer tok"}

    def test_files_outside_the_roots_are_not_sent(self, project):
        (project / "conftest.py").write_text("x = 1\n")
        err = ERROR + "conftest.py:3: in fixture\n/etc/passwd.py:1: in x\n../escape.py:1: in y\n"
        stack = stack_from_error(err, ("pages", "tests", "utils"), project)
        assert all(f["file"].split("/")[0] in ("pages", "tests") for f in stack)
        assert [f["path"] for f in collect_source(stack, ("pages", "tests", "utils"), project)] == [
            "pages/login_page.py", "tests/test_login.py"]

    def test_caps_twenty_files_and_256_kb_each(self, project):
        for i in range(25):
            (project / "pages" / f"p{i}.py").write_text("x = 1\n")
        (project / "pages" / "big.py").write_text("#" * (256 * 1024 + 1))
        (project / "pages" / "edge.py").write_text("#" * (256 * 1024))
        stack = [{"file": f"pages/p{i}.py", "line": 1} for i in range(25)] + [
            {"file": "pages/big.py", "line": 1}, {"file": "pages/edge.py", "line": 1}]
        files = collect_source(stack, ("pages",), project)
        assert len(files) == 20 and "pages/big.py" not in {f["path"] for f in files}
        assert "pages/edge.py" not in {f["path"] for f in files}          # past the 20-file cap
        only = collect_source(stack[-2:], ("pages",), project)
        assert [f["path"] for f in only] == ["pages/edge.py"]

    def test_symlink_that_leaves_the_repo_is_not_sent(self, project, tmp_path_factory):
        outside = tmp_path_factory.mktemp("outside") / "secret.py"
        outside.write_text("TOKEN = 1\n")
        (project / "pages" / "link.py").symlink_to(outside)
        assert collect_source([{"file": "pages/link.py", "line": 1}], ("pages",), project) == []

    def test_test_id_from_the_junit_classname(self, project):
        assert junit_test_id("tests.test_login", "test_a", project) == "tests/test_login.py::test_a"
        assert junit_test_id("tests.test_login.TestX", "test_a", project) == "tests/test_login.py::TestX::test_a"
        assert junit_test_id("nowhere.mod", "t", project) == "nowhere.mod::t"

    def test_last_pass_and_its_route_come_from_the_fingerprint_file(self, project, monkeypatch):
        monkeypatch.delenv("HEAL_DIR", raising=False)
        key = fp.call_key("pages/login_page.py", "await self.page.locator('#username').fill(user)")
        fp.merge_into(project, {
            key: {"file": "pages/login_page.py", "text": "x", "page": "/secure/login", "language": "fr",
                  "fingerprint": {"tag": "input", "attrs": {"id": "username"}}},
            "tests/x.py::b": {"file": "tests/x.py", "text": "b", "page": "/secure/login", "language": "fr",
                              "fingerprint": {"tag": "button", "text": "Go"}},
            "tests/x.py::c": {"file": "tests/x.py", "text": "c", "page": "/elsewhere", "language": "fr",
                              "fingerprint": {"tag": "a"}}}, env={})
        svc, routes = FakeService(reply("not_drift")), []
        h = Healer(svc.client(), HealSettings(), Verify(), root=project,
                   live_factory=lambda route, probe: routes.append(route) or FakeLive())
        h.heal(FAILURE)
        lp = svc.posts("/v1/heal")[0]["last_pass"]
        assert routes == ["/secure/login"] and "_page" not in lp
        assert lp["fingerprint"] == {"tag": "input", "attrs": {"id": "username"}} and lp["language"] == "fr"
        assert lp["neighbours"] == [{"tag": "button", "text": "Go"}]      # same page only

    def test_route_falls_back_to_the_page_objects_self_url_then_root(self, project):
        svc, routes = FakeService(reply("not_drift")), []
        Healer(svc.client(), HealSettings(), Verify(), root=project,
               live_factory=lambda route, probe: routes.append(route) or FakeLive()).heal(FAILURE)
        assert routes == ["/login"]


# ---- the loop ----------------------------------------------------------------------------------------------------------
class TestLoop:
    def test_healed_keeps_the_edit_after_a_check_a_rerun_and_a_report(self, project):
        svc = FakeService(reply("try", candidate(project)), reply("healed", candidate(project), rnd=1))
        verify = Verify(True, root=project)
        h = healer(project, svc, verify)
        d = h.heal(FAILURE)
        text = (project / "pages/login_page.py").read_text()
        assert d["outcome"] == "healed" and d["file"] == "pages/login_page.py" and d["from"] == FROM and d["to"] == TO
        assert text.count(TO) == 1 and text.count(FROM) == 1             # only the diagnosed occurrence changed
        assert TO in verify.seen[0]                                        # the re-run saw the edited file
        assert svc.posts("/result") == [{"count": 1, "hit": {"ref": "e0"}, "test_outcome": "passed"}]
        assert h.live.asked == [TO]
        assert d["usage"] == {"calls": 1, "input_tokens": 100, "output_tokens": 9, "images": 0}

    def test_wrong_count_edits_nothing_and_tries_the_next_candidate(self, project):
        live = FakeLive({TO: (2, None)})
        svc = FakeService(reply("try", candidate(project)), reply("needs_human", reason="no_candidate_left", why="none left"))
        verify = Verify()
        d = healer(project, svc, verify, live).heal(FAILURE)
        assert (project / "pages/login_page.py").read_text() == PAGE_SRC and verify.calls == 0
        assert svc.posts("/result") == [{"count": 2}]
        assert d["outcome"] == "needs_human" and d["reason"] == "no_candidate_left"

    def test_wrong_element_edits_nothing_and_names_the_hit(self, project):
        live = FakeLive({TO: (1, "e5")}, inventory=[{"ref": "e0", "tag": "input"}, {"ref": "e5", "tag": "input"}])
        svc = FakeService(reply("try", candidate(project)), reply("needs_human", reason="max_rounds"))
        verify = Verify()
        healer(project, svc, verify, live).heal(FAILURE)
        assert (project / "pages/login_page.py").read_text() == PAGE_SRC and verify.calls == 0
        assert svc.posts("/result") == [{"count": 1, "hit": {"ref": "e5"}}]

    def test_a_hit_that_cannot_be_named_is_not_a_pass(self, project):
        live = FakeLive({TO: (1, None)})
        svc = FakeService(reply("try", candidate(project)), reply("needs_human", reason="x"))
        verify = Verify()
        healer(project, svc, verify, live).heal(FAILURE)
        assert verify.calls == 0 and svc.posts("/result") == [{"count": 1}]

    def test_failed_rerun_reverts_and_reports_failed_then_moves_on(self, project):
        second = candidate(project, to="self.page.locator('#user')")
        svc = FakeService(reply("try", candidate(project)), reply("try", second, rnd=2),
                          reply("healed", second, rnd=2))
        verify = Verify(False, True, root=project)
        d = healer(project, svc, verify).heal(FAILURE)
        assert TO in verify.seen[0] and "#user" in verify.seen[1]
        text = (project / "pages/login_page.py").read_text()
        assert TO not in text and text.count("locator('#user')") == 1                 # the first try was reverted before the second
        assert [r["test_outcome"] for r in svc.posts("/result")] == ["failed", "passed"]
        assert d["outcome"] == "healed" and d["to"] == "self.page.locator('#user')"

    def test_every_candidate_failing_leaves_the_file_as_it_was(self, project):
        svc = FakeService(reply("try", candidate(project)), reply("needs_human", reason="max_rounds", why="rounds"))
        d = healer(project, svc, Verify(False, root=project)).heal(FAILURE)
        assert (project / "pages/login_page.py").read_bytes() == PAGE_SRC.encode() and d["outcome"] == "needs_human"

    def test_a_pass_the_service_does_not_confirm_is_reverted(self, project):
        svc = FakeService(reply("try", candidate(project)), reply("needs_human", reason="odd"))
        d = healer(project, svc, Verify(True, root=project)).heal(FAILURE)
        assert (project / "pages/login_page.py").read_text() == PAGE_SRC and d["outcome"] == "needs_human"

    def test_losing_the_service_after_a_pass_reverts_the_edit(self, project):
        svc = FakeService(reply("try", candidate(project)))               # no reply left for /result: the pop raises
        svc.handler_orig = svc.handler

        def handler(request):
            if request.url.path.endswith("/result"):
                return httpx.Response(503, json={"detail": "down"})
            return svc.handler_orig(request)
        client = ServiceClient("http://svc", "", httpx.Client(transport=httpx.MockTransport(handler)))
        h = Healer(client, HealSettings(), Verify(True, root=project), root=project, live_factory=lambda r, p: FakeLive())
        d = h.heal(FAILURE)
        assert (project / "pages/login_page.py").read_text() == PAGE_SRC
        assert d["outcome"] == "needs_human" and d["reason"] == "service_error" and "503" in d["why"]

    def test_a_crash_in_the_rerun_reverts(self, project):
        svc = FakeService(reply("try", candidate(project)))

        def verify(test):
            raise RuntimeError("pytest vanished")
        d = healer(project, svc, verify).heal(FAILURE)
        assert (project / "pages/login_page.py").read_text() == PAGE_SRC
        assert d["outcome"] == "needs_human" and d["reason"] == "client_error" and "pytest vanished" in d["why"]

    def test_also_patches_apply_with_the_main_patch_in_one_go(self, project):
        also = [patch_for(project, TO, nth=1), patch_for(project, TO, file="pages/other_page.py")]
        cand = candidate(project, also=also)
        svc = FakeService(reply("try", cand), reply("healed", cand))
        d = healer(project, svc, Verify(True, root=project)).heal(
            {**FAILURE, "error": ERROR + "pages/other_page.py:1: in z\n"})
        assert (project / "pages/login_page.py").read_text().count(TO) == 2
        assert d["outcome"] == "healed" and sorted(d["files"]) == ["pages/login_page.py", "pages/other_page.py"]

    def test_service_error_becomes_a_decision_not_a_crash(self, project):
        d = healer(project, FakeService(status=500), Verify()).heal(FAILURE)
        assert d["outcome"] == "needs_human" and d["reason"] == "service_error" and "500" in d["why"] and "boom" in d["why"]

    def test_unreachable_service_becomes_a_decision(self, project):
        def handler(request):
            raise httpx.ConnectError("refused")
        client = ServiceClient("http://svc", "", httpx.Client(transport=httpx.MockTransport(handler)))
        d = Healer(client, HealSettings(), Verify(), root=project, live_factory=lambda r, p: FakeLive()).heal(FAILURE)
        assert d["outcome"] == "needs_human" and d["reason"] == "service_error" and "could not be reached" in d["why"]

    def test_browser_failure_becomes_a_decision(self, project):
        def boom(route, probe):
            raise RuntimeError("chromium missing")
        d = Healer(FakeService().client(), HealSettings(), Verify(), root=project, live_factory=boom).heal(FAILURE)
        assert d["outcome"] == "needs_human" and d["reason"] == "client_error"

    def test_needs_human_and_not_drift_carry_the_services_reason(self, project):
        svc = FakeService(reply("needs_human", reason="target_missing", why="no element could be the one"))
        d = healer(project, svc, Verify()).heal(FAILURE)
        assert d["outcome"] == "needs_human" and d["reason"] == "target_missing" and "no element" in d["why"]

    def test_run_total_sums_usage(self):
        ds = [{"usage": {"calls": 1, "input_tokens": 100, "output_tokens": 9}}, {"usage": {}}, {}]
        assert run_total(ds) == {"calls": 1, "input_tokens": 100, "output_tokens": 9, "images": 0}


# ---- patch safety refusals ---------------------------------------------------------------------------------------------
class TestPatchSafety:
    def run(self, project, cand, *later):
        svc = FakeService(reply("try", cand), *later)
        verify = Verify(root=project)
        d = healer(project, svc, verify).heal(FAILURE)
        return d, svc, verify

    def untouched(self, project):
        assert (project / "pages/login_page.py").read_text() == PAGE_SRC

    def test_stale_base_hash_is_refused_and_ends_the_heal(self, project):
        d, svc, verify = self.run(project, candidate(project, base="0" * 64))
        self.untouched(project)
        assert d["outcome"] == "needs_human" and d["reason"] == "patch_refused" and "base hash" in d["why"]
        assert verify.calls == 0 and "patch refused" in svc.posts("/result")[0]["error"]

    def test_a_file_changed_after_the_request_is_refused(self, project):
        cand = candidate(project)
        (project / "pages/login_page.py").write_text(PAGE_SRC + "# edited meanwhile\n")
        d, svc, verify = self.run(project, cand)
        assert d["reason"] == "patch_refused" and verify.calls == 0
        assert (project / "pages/login_page.py").read_text().endswith("# edited meanwhile\n")

    @pytest.mark.parametrize("file", ["conftest.py", "../outside.py", "/etc/hosts", "pages/../conftest.py", "scripts/heal.py"])
    def test_a_file_outside_the_source_roots_is_refused(self, project, file):
        cand = candidate(project)
        cand["patch"]["file"] = file
        d, _, verify = self.run(project, cand)
        assert d["reason"] == "patch_refused" and "source roots" in d["why"] and verify.calls == 0
        self.untouched(project)

    def test_a_file_that_was_never_sent_is_refused(self, project):
        d, _, verify = self.run(project, candidate(project, file="pages/other_page.py", frm="self.page.locator('#username')"))
        assert d["reason"] == "patch_refused" and "not one of the files sent" in d["why"] and verify.calls == 0

    def test_a_span_that_does_not_hold_from_is_refused(self, project):
        cand = candidate(project)
        cand["patch"]["span"] = {"start": 0, "end": len(FROM)}
        d, _, verify = self.run(project, cand)
        assert d["reason"] == "patch_refused" and "span" in d["why"] and verify.calls == 0
        self.untouched(project)

    def test_a_span_past_the_end_is_refused(self, project):
        cand = candidate(project)
        cand["patch"]["span"] = {"start": 10**6, "end": 10**6 + 3}
        assert self.run(project, cand)[0]["reason"] == "patch_refused"

    def test_overlapping_spans_are_refused(self, project):
        main = candidate(project)
        overlap = patch_for(project, "page.get_by_test_id('x')", frm="page.locator('#username')")
        assert overlap["span"]["start"] == main["patch"]["span"]["start"] + 5      # inside the main patch's span
        d, *_ = self.run(project, candidate(project, also=[overlap]))
        assert d["reason"] == "patch_refused"

    @pytest.mark.parametrize("bad", [
        "__import__('os').system('id')", "self.page.locator('#a'); import os", "self.page.get_by_label('a')\nimport os",
        "other.get_by_label('a')", "self.page.evaluate('1')", "self.page.get_by_label(open('/etc/passwd').read())",
        FROM,
    ])
    def test_an_unsafe_replacement_is_refused_but_the_next_candidate_is_still_tried(self, project, bad):
        good = candidate(project, to="self.page.locator('#user')")
        svc = FakeService(reply("try", candidate(project, to=bad)), reply("try", good, rnd=2), reply("healed", good, rnd=2))
        verify = Verify(True, root=project)
        d = healer(project, svc, verify).heal(FAILURE)
        assert verify.calls == 1 and "#user" in verify.seen[0] and d["outcome"] == "healed"
        first = svc.posts("/result")[0]
        assert first["count"] is None and first["error"]

    def test_an_unsafe_also_patch_refuses_the_whole_candidate(self, project):
        also = [patch_for(project, "__import__('os').system('x')", nth=1)]
        good = candidate(project, to="self.page.locator('#user')")
        svc = FakeService(reply("try", candidate(project, also=also)), reply("needs_human", reason="no_candidate_left"))
        d = healer(project, svc, Verify(root=project)).heal(FAILURE)
        self.untouched(project)                        # the main patch was not applied on its own
        assert d["outcome"] == "needs_human" and good

    def test_an_unsafe_locator_is_not_even_checked_in_the_live_page(self, project):
        live = FakeLive()
        svc = FakeService(reply("try", candidate(project, to="__import__('os').system('id')")),
                          reply("needs_human", reason="x"))
        healer(project, svc, Verify(), live).heal(FAILURE)
        assert live.asked == []
        assert svc.posts("/result") == [{"count": None, "error": "the locator is not a safe expression"}]


# ---- language branches -------------------------------------------------------------------------------------------------
BR = {"en": "self.page.get_by_label('Username')", "fr": "self.page.get_by_label(\"Nom d'utilisateur\")"}
BR_TO = 'by_language(self.page, {"en": ' + BR["en"] + ', "fr": ' + BR["fr"] + "})"


class TestBranches:
    def test_branch_code_checks_the_page_language_branch_and_adds_the_helper_import(self, project):
        cand = candidate(project, to=BR_TO, branches=BR)
        svc = FakeService(reply("try", cand), reply("healed", cand))
        live = FakeLive(language="fr")
        live.language = "fr"
        d = healer(project, svc, Verify(True, root=project), live).heal(FAILURE)
        text = (project / "pages/login_page.py").read_text()
        assert live.asked == [BR["fr"]]                              # the branch of the page's language is the one checked
        assert BR_TO in text and "from utils.heal_locale import by_language\n" in text
        assert text.index("from utils.heal_locale") < text.index("class LoginPage")
        assert d["outcome"] == "healed"

    def test_a_page_language_with_no_branch_is_reported_as_unchecked(self, project):
        cand = candidate(project, to=BR_TO, branches=BR)
        svc = FakeService(reply("try", cand), reply("needs_human", reason="max_rounds"))
        live = FakeLive(language="de")
        healer(project, svc, Verify(), live).heal(FAILURE)
        assert svc.posts("/result")[0]["count"] is None and (project / "pages/login_page.py").read_text() == PAGE_SRC

    def test_each_branch_is_validated_on_its_own(self):
        bad_branches = {"en": BR["en"], "fr": "__import__('os').system('x')"}
        to = 'by_language(self.page, {"en": ' + BR["en"] + ', "fr": __import__(\'os\').system(\'x\')})'
        assert "safe locator" in check_replacement(to, FROM, bad_branches)
        assert check_replacement(BR_TO, FROM, BR) is None

    @pytest.mark.parametrize("to,why", [
        ('by_language(other, {"en": ' + BR["en"] + ', "fr": ' + BR["fr"] + "})", "receiver"),
        ('by_language(self.page, {"en": ' + BR["en"] + ', "de": ' + BR["fr"] + "})", "languages"),
        ('by_language(self.page, {"en": ' + BR["en"] + ', "fr": self.page.get_by_label("x")})', "differs"),
        ('by_language(self.page, {"EN": ' + BR["en"] + ', "fr": ' + BR["fr"] + "})", "matching"),
        ("self.page.get_by_label('x')", "matching"),
        ('by_language(self.page, {"en": ' + BR["en"] + "})", "languages"),
    ])
    def test_code_that_does_not_match_its_branches_is_refused(self, to, why):
        assert why in check_replacement(to, FROM, BR)

    def test_branch_code_without_branches_is_refused(self):
        assert check_replacement(BR_TO, FROM, None) is not None

    def test_also_patch_keeps_its_own_receiver(self):
        other = BR_TO.replace("self.page", "page")
        assert check_replacement(other, "page.locator('#a')", BR, exact_branches=False) is None


# ---- walking an approved expression ------------------------------------------------------------------------------------
class Recorder:
    """Stands in for a Playwright page: every approved method call comes back as a recorded step."""

    def __init__(self, steps=()):
        self.steps = tuple(steps)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if name in ("first", "last"):
            return Recorder(self.steps + ((name,),))
        return lambda *a, **k: Recorder(self.steps + ((name, a, k),))


class TestBuildLocator:
    def test_walks_an_approved_chain(self):
        loc = build_locator(Recorder(), "self.page.get_by_role('button', name='Go', exact=True).first")
        assert loc.steps == (("get_by_role", ("button",), {"name": "Go", "exact": True}), ("first",))

    def test_page_and_self_page_are_the_same_receiver(self):
        assert build_locator(Recorder(), "page.locator('#a')").steps == (("locator", ("#a",), {}),)

    @pytest.mark.parametrize("bad", [
        "self.page.evaluate('1')", "__import__('os').getcwd()", "other.locator('#a')", "self.page.locator(x)",
        "self.page.locator('#a').click()", "self.page.locator(", "self.browser.locator('#a')",
    ])
    def test_anything_else_is_never_run(self, bad):
        assert build_locator(Recorder(), bad) is None


class TestMatchRef:
    INV = [{"ref": "e0", "tag": "input", "id": "a", "box": {"x": 1, "y": 2, "width": 3, "height": 4}},
           {"ref": "e1", "tag": "input", "id": "b", "box": {"x": 9, "y": 2, "width": 3, "height": 4}}]

    def test_exact_match(self):
        assert match_ref(self.INV, {"tag": "input", "id": "b", "box": self.INV[1]["box"]}) == "e1"

    def test_a_near_miss_that_differs_in_box_or_frame_names_nothing(self):
        assert match_ref(self.INV, {"tag": "input", "id": "b", "frame": "f", "box": None}) is None
        assert match_ref(self.INV, {"tag": "input", "id": "b", "box": {"x": 9, "y": 2, "width": 3, "height": 4}}) == "e1"

    def test_ambiguous_or_unknown_is_none(self):
        twin = self.INV + [{"ref": "e2", "tag": "input", "id": "b", "box": None}]
        assert match_ref(twin, {"tag": "input", "id": "b", "box": None}) == "e2"
        assert match_ref(twin, {"tag": "input", "id": "b", "box": {"x": 0, "y": 0, "width": 1, "height": 1}}) is None
        assert match_ref(self.INV, {"tag": "select"}) is None


class TestSettings:
    def test_defaults_and_accepted_unused_options(self):
        s = HealSettings.from_env({"HEAL_SERVICE_URL": "http://localhost:8765/", "HEAL_VISION": "AUTO",
                                   "HEAL_MASK": "#pw, .card\n.ssn, .dob ;;  [data-x='a;b']", "HEAL_TEST_ID_ATTRIBUTE": "data-qa"})
        assert (s.url, s.vision, s.mask, s.test_id_attribute) == (
            "http://localhost:8765", "auto", ["#pw, .card", ".ssn, .dob", "[data-x='a;b']"], "data-qa")
        assert HealSettings.from_env({}).test_id_attribute == "data-testid"
        assert HealSettings.from_env({"HEAL_TEST_ID_ATTRIBUTE": "bad attr!"}).test_id_attribute == "data-testid"

    def test_service_errors_name_status_and_reason_never_the_request(self):
        svc = FakeService(status=422)
        with pytest.raises(HealServiceError) as e:
            svc.client().heal({"secret": "x"})
        assert "422" in str(e.value) and "boom" in str(e.value) and "secret" not in str(e.value)


# ---- the heal passes its own line and the test stops later --------------------------------------------------------------
def later_error(file="pages/login_page.py", line=11, message="TimeoutError: waiting for locator('#other')"):
    return {"name": "test_valid_login", "classname": "tests.test_login", "outcome": "failed",
            "error": f"tests/test_login.py:2: in test_valid_login\n    await LoginPage(page).login('u')\n"
                     f"{file}:{line}: in login\n    await x\nE   {message}\n"}


class TestFailedLater:
    def run(self, project, verify_result, *replies):
        svc = FakeService(reply("try", candidate(project)), *replies)
        verify = Verify(verify_result, root=project)
        d = healer(project, svc, verify).heal(FAILURE)
        return d, svc, verify, (project / "pages/login_page.py").read_text()

    def test_a_failure_on_a_later_line_is_reported_as_failed_later_and_kept_when_the_service_says_healed(self, project):
        failure = later_error()
        d, svc, verify, text = self.run(project, (False, failure),
                                        reply("healed", candidate(project), reason="later_locator"))
        assert svc.posts("/result") == [{"count": 1, "hit": {"ref": "e0"}, "test_outcome": "failed_later", "later": {
            "error": redact_failure_text(failure["error"]), "file": "pages/login_page.py", "line": 11}}]
        assert d["outcome"] == "healed" and d["reason"] == "later_locator" and TO in text
        assert d["later_failure"] == failure                       # the next round heals this failure

    def test_the_patch_is_still_on_disk_while_the_service_decides(self, project):
        seen = []
        svc = FakeService(reply("try", candidate(project)), reply("healed", candidate(project), reason="later_locator"))
        orig = svc.handler

        def spy(request):
            if request.url.path.endswith("/result"):
                seen.append(TO in (project / "pages/login_page.py").read_text())
            return orig(request)
        svc.handler = spy
        healer(project, svc, Verify((False, later_error()), root=project)).heal(FAILURE)
        assert seen == [True]

    @pytest.mark.parametrize("status,reason", [("try", None), ("needs_human", "failed_rerun")])
    def test_it_is_reverted_when_the_service_does_not_confirm(self, project, status, reason):
        replies = [reply(status, candidate(project) if status == "try" else None, reason=reason)]
        if status == "try":
            replies.append(reply("needs_human", reason="no_candidate_left", why="none left"))
        d, svc, _, text = self.run(project, (False, later_error()), *replies)
        assert text == PAGE_SRC and d["outcome"] == "needs_human" and "later_failure" not in d
        assert svc.posts("/result")[0]["test_outcome"] == "failed_later"

    def test_a_failure_on_the_patched_line_is_reported_as_failed(self, project):
        d, svc, _, text = self.run(project, (False, later_error(line=10)),
                                   reply("needs_human", reason="failed_rerun", why="still fails"))
        assert svc.posts("/result") == [{"count": 1, "hit": {"ref": "e0"}, "test_outcome": "failed"}]
        assert text == PAGE_SRC and d["outcome"] == "needs_human"

    def test_a_failure_in_another_file_counts_as_a_different_line(self, project):
        (project / "pages" / "other.py").write_text("x = 1\n")
        d, svc, *_ = self.run(project, (False, later_error(file="pages/other.py", line=10)),
                              reply("healed", candidate(project), reason="later_locator"))
        assert svc.posts("/result")[0]["later"]["file"] == "pages/other.py" and d["outcome"] == "healed"

    def test_a_failure_whose_place_is_unknown_is_reported_as_failed(self, project):
        bare = {"name": "test_valid_login", "classname": "tests.test_login", "outcome": "failed", "error": "boom\n"}
        _, svc, *_ = self.run(project, (False, bare), reply("needs_human", reason="failed_rerun", why="x"))
        assert svc.posts("/result")[0]["test_outcome"] == "failed"

    def test_a_bool_result_without_a_failure_is_a_plain_failed_rerun(self, project):
        _, svc, *_ = self.run(project, False, reply("needs_human", reason="failed_rerun", why="x"))
        assert svc.posts("/result")[0] == {"count": 1, "hit": {"ref": "e0"}, "test_outcome": "failed"}

    def test_the_later_error_is_capped_at_4000_characters(self, project):
        _, svc, *_ = self.run(project, (False, later_error(message="\n".join(["Timeout 30000ms exceeded."] * 400))),
                              reply("needs_human", reason="failed_rerun", why="x"))
        assert len(svc.posts("/result")[0]["later"]["error"]) == 4000

    def test_the_later_error_is_redacted_like_the_request_failure(self, project):
        failure = later_error(message="AssertionError: assert 'hunter2secret' == 'x'")
        _, svc, *_ = self.run(project, (False, failure), reply("needs_human", reason="failed_rerun", why="x"))
        error = svc.posts("/result")[0]["later"]["error"]
        assert error == redact_failure_text(failure["error"]) and "hunter2secret" not in error

    def test_the_next_round_heals_the_later_failure_on_top_of_the_kept_patch(self, project, tmp_path_factory):
        after_first = tmp_path_factory.mktemp("after_first")        # what the file holds once round 1 is kept
        (after_first / "pages").mkdir()
        (after_first / "pages" / "login_page.py").write_text(PAGE_SRC.replace(FROM, TO, 1))
        to2 = "self.page.get_by_test_id('login-user-2')"
        svc = FakeService(
            reply("try", candidate(project)), reply("healed", candidate(project), reason="later_locator"),
            reply("try", candidate(after_first, to=to2), hid="h_2"), reply("healed", candidate(after_first, to=to2), hid="h_2"))
        verify = Verify((False, later_error()), True, root=project)
        h = healer(project, svc, verify)
        first = h.heal(FAILURE)
        second = h.heal(first.pop("later_failure"))
        text = (project / "pages/login_page.py").read_text()
        assert first["outcome"] == "healed" and second["outcome"] == "healed" and TO in text and to2 in text and FROM not in text
        assert svc.posts("/v1/heal")[1]["failure"]["stack"][0] == {"file": "pages/login_page.py", "line": 11}
        assert [b["test_outcome"] for b in svc.posts("/result")] == ["failed_later", "passed"]


def test_written_lines_follow_an_added_import_and_a_replaced_line():
    from utils.heal_client import PlannedFile, _written_lines
    before = "import os\n\nx = a.locator('#u')\ny = 2\n"
    after = "import os\nfrom helper import h\n\nx = a.get_by_test_id('u')\ny = 2\n"
    assert _written_lines(PlannedFile("p.py", before.encode(), after)) == {2, 4}
