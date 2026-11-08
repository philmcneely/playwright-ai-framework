"""
===============================================================================
Unit Tests: hardening of the heal client and advice path (security review of phase 4)
===============================================================================
No assertion value, local variable, element HTML or code-frame source line leaves in the failure text (and the service's own
triage still reads what is left); a PR address must match in full and name the pinned host; service text in a report stays
inside code spans; a client caps rounds, reports coarse counts, refuses attribute-operator and value selectors, accepts only a
same-origin path as the page route and keeps its origin guard on from the first navigation with service workers blocked; the
aria snapshot loses link queries, the chosen option and the text of contenteditable regions; a lone surrogate is refused; and
every POST says it carries JSON.

Author: PMAC
===============================================================================
"""
import json
from types import SimpleNamespace

import httpx
import pytest

from utils import heal_advise as ha
from utils import heal_client as hc
from utils import heal_followup as hf
from utils.heal_client import HealServiceError, HealSettings, Healer, ServiceClient, check_replacement, safe_route
from utils.heal_redact import redact_failure_text, redact_typed_values, scrub_texts
from tests.unit.test_heal_contract import FakeLive, FakeService, load

PR = "https://github.com/example-org/shop-e2e/pull/42"
FROM = "self.page.locator('#username')"


# ---- Content-Type ---------------------------------------------------------------------------------------------------------
def test_every_post_the_client_makes_says_it_carries_json():
    seen = []

    def handler(req):
        seen.append((req.method, req.url.path, req.headers.get("content-type")))
        return httpx.Response(200, json={})
    c = ServiceClient("http://localhost:8765", "tok", http=httpx.Client(transport=httpx.MockTransport(handler)))
    c.heal({}), c.result("h_a", {}), c.followup("h_a", {}), c.capabilities()
    assert [(m, ct) for m, p, ct in seen if m == "POST"] == [("POST", "application/json")] * 3
    assert [ct for m, p, ct in seen if m == "GET"] == [None]


# ---- L3: the failure text -------------------------------------------------------------------------------------------------
ERROR = """tests/test_login.py:9: in test_login
    await page.fill("#pw", "hunter2")
pages/login_page.py:6: in login
    await self.page.locator('#password').fill(pw)
pw = 'hunter2'
self = <pages.login_page.LoginPage object at 0x10c>
>       await self.page.locator('#password').fill(pw)
E       playwright._impl._errors.TimeoutError: Locator.fill: Timeout 30000ms exceeded.
E       Call log:
E         - waiting for locator('#password')
E         -   locator resolved to <input type="password" value="hunter2"/>
E       Expected string: "secret expected"
E       Received string: "secret received"
E       Actual value: hunter2@corp.example
"""


def kept(text):
    return redact_failure_text(text)


def test_no_assertion_value_local_variable_element_html_or_code_frame_line_leaves():
    out = kept(ERROR)
    for secret in ("hunter2", "secret expected", "secret received", "corp.example", "LoginPage object", "type=\"password\"",
                   "await page.fill", "pw ="):
        assert secret not in out, secret
    assert "waiting for locator('#password')" in out and "Timeout 30000ms exceeded" in out and "resolved to <element>" in out


def test_a_strict_mode_listing_loses_its_element_html_but_keeps_the_count():
    err = ("E   Error: strict mode violation: locator('button') resolved to 2 elements:\n"
           "E       1) <button value=\"s3cret\">Save</button> aka get_by_role('button', name='Save')\n"
           "E       2) <button>Cancel</button> aka get_by_role('button', name='Cancel')\n")
    out = kept(err)
    assert "resolved to 2 elements" in out and "s3cret" not in out and "<button" not in out


def test_the_service_triage_reads_the_cut_text_as_it_read_the_whole(tmp_path):
    triage = pytest.importorskip("heal_service.triage").triage
    src = ("class LoginPage:\n    def __init__(self, page):\n        self.page = page\n\n    async def login(self, pw):\n"
           "        await self.page.locator('#password').fill(pw)\n")
    f = SimpleNamespace(path="pages/login_page.py", content=src, digest="d")
    stack = [("pages/login_page.py", 6)]
    for err in (ERROR,
                "E  AssertionError: Locator expected to have text\nE  locator resolved to <h1>Welcome Bob</h1>\n"
                "E  Expected string: \"Welcome\"\nE  Received string: \"Hello\"\n",
                "AssertionError: assert 'a' == 'b'\n", "E  Error: strict mode violation: locator('#password') resolved to 2 elements:\n"):
        whole, cut = triage(err, [f], stack, "python"), triage(kept(err), [f], stack, "python")
        assert (cut.status, cut.reason, cut.call, cut.line, cut.action) == (whole.status, whole.reason, whole.call, whole.line, whole.action), err


def test_build_request_sends_only_the_cut_failure_text(tmp_path):
    page = {"path": "/", "language": {}, "inventory": [], "more": 0, "viewport": {}, "aria": None}
    req = hc.build_request({"name": "t", "classname": "", "error": ERROR}, [], [], page, HealSettings(), tmp_path, mode="advise")
    assert "hunter2" not in json.dumps(req) and "waiting for locator('#password')" in req["failure"]["error"]


# ---- L4: the PR address and the record file -------------------------------------------------------------------------------
@pytest.mark.parametrize("url,ok", [(PR, True), (PR + "\n", False), ("\n" + PR, False), (PR + "/files", False),
                                    ("https://github.com/o/r/pull/1#x", False), ("https://169.254.169.254/o/r/pull/1", False),
                                    ("https://github.com.evil.example/o/r/pull/1", False), ("http://github.com/o/r/pull/1", False)])
def test_a_pr_address_matches_in_full_on_the_pinned_host(url, ok):
    assert hf.is_pr_url(url, {}) is ok


def test_the_host_is_pinned_to_github_unless_the_operator_names_another():
    ghe = {"HEAL_GH_HOST": "git.example.com"}
    assert hf.is_pr_url("https://git.example.com/o/r/pull/3", ghe) and not hf.is_pr_url(PR, ghe)
    assert hf.pr_host({"HEAL_GH_HOST": "bad host/x"}) == "github.com" and hf.pr_host({}) == "github.com"
    calls = []
    assert hf.gh_state("https://evil.example.com/o/r/pull/1", run=lambda a, **k: calls.append(a)) is None and calls == []


def test_a_trailing_newline_never_passes_an_anchor():
    base = {"file": "pages/a.py", "from": "x", "to": "y", "test": "t", "pr_url": PR, "opened_at": 1, "heal_id": "h_abc"}
    assert hf._entry({**base, "heal_id": "h_abc\n"}, {}) is None and hf._entry({**base, "pr_url": PR + "\n"}, {}) is None
    assert hf._entry(base, {})["heal_id"] == "h_abc"


def test_one_bad_entry_never_stops_the_others(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "a.py").write_text("y")
    for i in (1, 2, 3):
        hf.record_heals(tmp_path, [{"test": f"t{i}", "heal_id": f"h_{i}", "file": "pages/a.py", "from": "x", "to": "y"}],
                        f"https://github.com/o/r/pull/{i}", now=1000.0, env={})
    sent = []

    class Service:
        def followup(self, heal_id, body):
            if heal_id == "h_2":
                raise RuntimeError("boom")             # not a HealServiceError
            sent.append((heal_id, body))
    out = hf.follow_up(tmp_path, Service(), [], now=1000.0 + 86400, gh=lambda url: "merged", env={})
    assert [h for h, _ in sent] == ["h_1", "h_3"] and [o["heal_id"] for o in out] == ["h_1", "h_3"]


def test_a_followup_names_the_repo_and_run_the_heal_was_recorded_with(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "a.py").write_text("y")
    env = {"HEAL_REPO": "shop-e2e"}
    hf.record_heals(tmp_path, [{"test": "t", "heal_id": "h_1", "file": "pages/a.py", "from": "x", "to": "y"}], PR, now=0.0, env=env,
                    run_id="ci-7")
    sent = []
    hf.follow_up(tmp_path, SimpleNamespace(followup=lambda i, b: sent.append(b)), [], now=86400.0, gh=lambda u: "open", env=env)
    assert sent[0]["repo"] == "shop-e2e" and sent[0]["run_id"] == "ci-7"
    hf.record_heals(tmp_path, [{"test": "t2", "heal_id": "h_2", "file": "pages/a.py", "from": "x", "to": "y"}], PR, now=0.0, env={})
    assert [e["repo"] for e in hf.load(tmp_path, {})] == ["shop-e2e", ""]


# ---- L7: service text in the report ---------------------------------------------------------------------------------------
def test_service_text_in_the_report_is_inside_code_spans():
    d = ha.decision_of({"heal_id": "h_x", "status": "advised", "reason": "r", "why": "[click](https://evil.example) @team",
                        "usage": {}, "advice": {"code": "c", "strategy": "s`s", "tier": "t", "tier_movement": "up",
                                                "why": "# Heading ``` [x](y)", "alternatives": []}}, "t")
    text = ha.report_text(d, {"test_name": "[t](u)", "path": "/p", "error_message": "e", "timestamp": "now"})
    why = next(line for line in text.splitlines() if line.startswith("- **Why**"))
    assert why.startswith("- **Why**: `` ") or why.startswith("- **Why**: ```") or "`" in why.split(": ", 1)[1][:3]
    for line in text.splitlines():
        if "evil.example" in line or "@team" in line or "# Heading" in line:
            assert line.count("`") >= 2 and line.split("`", 1)[0].count("[") == 0
    assert ha._span("a`b``c") == "``` a`b``c ```" and ha._span("plain") == "` plain `"


# ---- (a) rounds, coarse counts, selectors -------------------------------------------------------------------------------------
def replay_setup(case, tmp_path, results):
    request = load(case, "request.json")
    files = {f["path"]: f["content"] for f in request["source"]["files"]}
    for path, content in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(content, encoding="utf-8")
    stack = request["failure"]["stack"]
    error = "\n".join(f"{f['file']}:{f['line']}: in frame" for f in reversed(stack)) + "\n" + request["failure"]["error"]
    service = FakeService(case, files, stack)
    service.script = {**service.script, "results": results}
    return request, service, error


class Forever(FakeService):
    """Always answers `try` with the first candidate, however the client reports."""

    def result(self, heal_id, report):
        self.reports.append(report)
        self.reported += 1
        return self._response(0)


def test_the_client_stops_at_its_own_round_limit_when_the_service_never_does(tmp_path):
    request, service, error = replay_setup("renamed_id_to_testid", tmp_path, [{"count": 2}] * 50)
    forever = Forever.__new__(Forever)
    forever.__dict__.update(service.__dict__)
    live = FakeLive(request, forever)
    healer = Healer(forever, HealSettings(roots=("pages",), base_url="http://app.example"), lambda f: False, root=tmp_path,
                    live_factory=lambda route, probe: live, run_id="r")
    d = healer.heal({"name": "t", "classname": "", "error": error})
    assert d["outcome"] == "needs_human" and d["reason"] == "max_rounds" and len(forever.reports) == 3
    assert (tmp_path / "pages" / "account_page.py").read_text() == next(iter({f["path"]: f["content"] for f in request["source"]["files"]}.values()))


@pytest.mark.parametrize("seen,sent", [(0, 0), (1, 1), (2, 2), (3, 2), (500, 2), (None, None)])
def test_a_candidate_that_misses_the_expected_element_reports_a_coarse_count(tmp_path, seen, sent):
    request, service, error = replay_setup("renamed_id_to_testid", tmp_path, [{"count": seen}, {"count": seen}])
    live = FakeLive(request, service)
    healer = Healer(service, HealSettings(roots=("pages",), base_url="http://app.example"), lambda f: False, root=tmp_path,
                    live_factory=lambda route, probe: live, run_id="r")
    try:
        healer.heal({"name": "t", "classname": "", "error": error})
    except AssertionError:
        pass                                            # the fake service runs out of steps: only the first report matters
    assert service.reports[0]["count"] == sent


@pytest.mark.parametrize("selector,ok", [("[data-qa='order-row-1']", True), ('[name="user"]', True), ("#user", True), ("tr.row", True),
                                         ("[id^='x']", False), ("[class*='btn']", False), ("[href$='.pdf']", False),
                                         ("[lang|='en']", False), ("[class~='a']", False), ("[value='hunter2']", False),
                                         ("input[value]", False), ("[ VALUE=x]", False), ("[defaultValue=x]", False)])
def test_attribute_operators_and_value_selectors_inside_locator_are_refused(selector, ok):
    to = f"self.page.locator({selector!r})"
    assert (check_replacement(to, FROM) is None) is ok, selector
    assert (hc.validate_replacement(to, FROM) is not None) is ok


# ---- (b) the route and the origin guard -------------------------------------------------------------------------------------
BASE = "http://localhost:7080"


@pytest.mark.parametrize("route,ok", [("/login", True), ("/a/b?x=1", True), ("/", True), ("//evil.example/x", False),
                                      ("http://evil.example/", False), ("https://localhost:7080/x", False), ("login", False),
                                      ("/a\\b", False), ("/\\evil.example", False), ("/a\nb", False), ("", False), (None, False),
                                      ("/x" * 2000, False), ("/\u202eevil", False)])
def test_the_route_is_a_plain_same_origin_path(route, ok):
    if ok:
        assert safe_route(route, BASE) == route
    else:
        with pytest.raises(ValueError):
            safe_route(route, BASE)


def test_a_route_from_the_fingerprint_file_that_leaves_the_origin_ends_the_heal_without_opening_a_browser(tmp_path):
    from utils import heal_fingerprints as fp
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "login_page.py").write_text("class P:\n    def go(self):\n        " + FROM + ".fill('x')\n")
    line = FROM + ".fill('x')"
    fp.merge_into(tmp_path, {fp.call_key("pages/login_page.py", line): {
        "file": "pages/login_page.py", "text": line, "page": "//evil.example/steal", "language": "en",
        "fingerprint": {"tag": "input", "attrs": {"id": "username"}}}}, env={})
    opened = []
    service = SimpleNamespace(probe_js=lambda: "", heal=lambda r: pytest.fail("no request may be made"))
    healer = Healer(service, HealSettings(base_url=BASE), lambda f: True, root=tmp_path,
                    live_factory=lambda route, probe: opened.append(route))
    err = "pages/login_page.py:3: in go\nE   waiting for locator('#username')\n"
    d = healer.heal({"name": "t", "classname": "", "error": err})
    assert d["outcome"] == "needs_human" and d["reason"] == "client_error" and opened == []


def test_the_live_page_blocks_service_workers_and_routes_before_the_first_navigation(monkeypatch):
    order = []

    class Page:
        def goto(self, route):
            order.append(("goto", route))

    class Ctx:
        def route(self, pattern, handler):
            order.append(("route", pattern))

        def new_page(self):
            return Page()

    class Browser:
        def new_context(self, **kw):
            order.append(("context", kw))
            return Ctx()

        def close(self):
            pass

    class Pw:
        chromium = SimpleNamespace(launch=lambda: Browser())

        def start(self):
            return self

        def stop(self):
            pass
    import playwright.sync_api as sync_api
    monkeypatch.setattr(sync_api, "sync_playwright", lambda: Pw())
    with hc.LivePage(HealSettings(base_url=BASE), "/login", "probe"):
        pass
    assert [o[0] for o in order] == ["context", "route", "goto"]
    assert order[0][1]["service_workers"] == "block" and order[1][1] == "**/*"


def test_the_guard_aborts_a_foreign_request_even_before_any_probe():
    guard = hc.OriginGuard(BASE)
    calls = []
    route = SimpleNamespace(request=SimpleNamespace(url="https://cdn.evil.example/x.js"), abort=lambda: calls.append("abort"),
                            continue_=lambda: calls.append("continue"))
    guard.handle(route)
    ok = SimpleNamespace(request=SimpleNamespace(url=BASE + "/app.js"), abort=lambda: calls.append("abort"),
                         continue_=lambda: calls.append("continue"))
    guard.handle(ok)
    assert calls == ["abort", "continue"]


# ---- (c) the aria snapshot ---------------------------------------------------------------------------------------------------
def test_link_queries_fragments_and_the_chosen_option_do_not_leave():
    out = redact_typed_values('- link "Reset":\n  - /url: /reset?token=abc123#frag\n  - /url: "https://h.example/p?x=1"\n'
                              '  - /url: /plain\n- combobox "Plan":\n  - option "Basic"\n  - option "Gold secret" [selected]\n')
    assert "abc123" not in out and "frag" not in out and "x=1" not in out and "Gold secret" not in out
    assert "/url: /reset" in out and "/url: /plain" in out and '/url: "https://h.example/p"' in out
    assert '- option "Basic"' in out and "- option [selected]" in out


def test_contenteditable_text_is_cut_from_the_snapshot_and_short_texts_are_left():
    aria = '- text: my secret note plain editable secret\n- button "Save"\n'
    out = scrub_texts(aria, ["my secret note", "plain editable secret", "a"])
    assert "secret" not in out and '- button "Save"' in out
    assert scrub_texts(aria, ["a", "bc"]) == aria and scrub_texts(aria, "not a list") == aria


def test_the_snapshot_functions_read_the_editable_text_only_to_cut_it_out():
    import asyncio

    class Page:
        url = BASE + "/"

        async def evaluate(self, script):
            if script == hc.EDITABLE_TEXTS_JS:
                return ["my secret note"]
            return {"page": {}, "items": [], "more": 0}

        def locator(self, sel):
            return SimpleNamespace(aria_snapshot=self._aria)

        async def _aria(self):
            return "- text: my secret note\n- link \"x\":\n  - /url: /a?t=1\n"
    snap = asyncio.run(ha.snapshot_page(Page()))
    assert "secret" not in snap["aria"] and "t=1" not in snap["aria"] and "/url: /a" in snap["aria"]


def _chromium():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _chromium(), reason="no Playwright Chromium build is installed")
def test_in_a_real_browser_none_of_the_page_secrets_survive_the_snapshot_path():
    from playwright.sync_api import sync_playwright
    html = ('<body><div contenteditable="true" aria-label="Notes">my secret note</div><select aria-label="Plan"><option>Basic</option>'
            '<option selected>Gold secret</option></select><a href="/reset?token=abc123#frag">Reset</a>'
            '<input aria-label="Name" value="typed secret"></body>')
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.set_content(html)
        live = hc.LivePage(HealSettings(), "/", hc.vendored_probe())
        live.page, live._response = page, None
        aria = live.snapshot()["aria"]
        b.close()
    for secret in ("my secret note", "Gold secret", "abc123", "frag", "typed secret"):
        assert secret not in aria, secret
    assert "Reset" in aria and "Basic" in aria


# ---- (d) a lone surrogate -----------------------------------------------------------------------------------------------------
def test_a_replacement_with_a_lone_surrogate_is_refused():
    for bad in ("self.page.locator('a\ud800b')", "self.page.get_by_text('\udfff')"):
        assert check_replacement(bad, FROM) is not None
    assert hc.validate_replacement("self.page.locator('a\ud800')", FROM) is None
    assert check_replacement("self.page.locator('caf\u00e9')", FROM) is None          # a real non-ASCII letter is fine


def test_a_lone_surrogate_in_service_text_cannot_break_the_report(tmp_path):
    d = ha.decision_of({"heal_id": "h", "status": "needs_human", "why": "bad \ud800 text", "usage": {}}, "t\udfff")
    assert "\ud800" not in json.dumps(d, ensure_ascii=False)
    path = ha.write_report(d, {"test_name": "t", "path": "/p", "error_message": "e"}, tmp_path)
    assert path.read_text(encoding="utf-8")


@pytest.mark.parametrize("bad", ["h_abc\n", "../x", "h_", "x_abc", "h_a/b", "h_a?x=1", "", None, "h_" + "a" * 65])
def test_a_heal_id_that_is_not_in_the_services_shape_never_becomes_a_path(bad):
    c = ServiceClient("http://localhost:8765", "", http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))))
    for call in (c.result, c.followup):
        with pytest.raises(HealServiceError):
            call(bad, {})
    assert c.result("h_abc123", {}) == {}


# ---- HEAL_ALLOW_ORIGINS -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value,want", [
    ("", ()), ("https://cdn.example", ("https://cdn.example",)),
    ("https://cdn.example, http://fonts.example:8080  wss://ws.example", ("https://cdn.example", "http://fonts.example:8080", "wss://ws.example")),
    ("*", ()), ("https://*.example", ()), ("https://cdn.example/path", ()), ("https://cdn.example?x=1", ()), ("cdn.example", ()),
    ("ftp://cdn.example", ()), ("https://cdn.example:99999", ()), ("https://CDN.Example,https://cdn.example", ("https://cdn.example",)),
    ("https://a.example;https://b.example", ()), ("https://[::1]:9000", ("https://[::1]:9000",))])
def test_allowed_origins_are_exact_scheme_host_port_entries(value, want):
    assert hc.parse_origins(value) == want
    assert HealSettings.from_env({"HEAL_ALLOW_ORIGINS": value}).allow_origins == want


def test_the_guard_lets_through_base_url_and_each_named_origin_and_nothing_wider():
    guard = hc.OriginGuard(BASE, hc.parse_origins("https://cdn.example http://fonts.example:8080"))
    calls = []

    def go(url):
        route = SimpleNamespace(request=SimpleNamespace(url=url), abort=lambda: calls.append("abort"),
                                continue_=lambda: calls.append("continue"))
        guard.handle(route)
    for url in (BASE + "/a.js", "https://cdn.example/x.js", "http://fonts.example:8080/f.woff", "https://cdn.example:444/x.js",
                "http://cdn.example/x.js", "https://sub.cdn.example/x.js", "https://evil.example/x.js", "http://fonts.example/f.woff"):
        go(url)
    assert calls == ["continue", "continue", "continue", "abort", "abort", "abort", "abort", "abort"]


def test_the_live_page_builds_its_guard_from_the_settings():
    live = hc.LivePage(HealSettings(base_url=BASE, allow_origins=("https://cdn.example",)), "/", "probe")
    assert hc._origin("https://cdn.example") in live.guard.allowed and live.guard.origin == hc._origin(BASE)
