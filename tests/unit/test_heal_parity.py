"""
===============================================================================
Unit Tests: the Python heal client holds the same lines as the TypeScript one
===============================================================================
One selector-refusal rule applied to EVERY expression built for the live page (a branch's page-language branch and an extra
patch included), the same list of refused forms as the TypeScript client, foreign WebSockets closed for the whole session,
one `_origin`, and the same screenshot masking (clear editable text, remember what was ever a password field, the same
autocomplete matching) without leaving a DOM attribute behind.

Author: PMAC
===============================================================================
"""
import base64
import http.server
import io
import threading

import pytest

from tests.unit.test_heal_client import FAILURE, FakeLive, FakeService, Verify, healer, project, reply, candidate  # noqa: F401
from utils import heal_client as hc

ORIG = "self.page.locator('#a')"
PROBES = ["text=/^a/i", "text=abc", "css=#a", "role=button", "id=a", "div[contenteditable]:has-text('a')",
          "div:text-matches('^a')", "input[type=hidden]", "input:nth-match(div, 2)", "div:text-is('a')", "#a >> text=b",
          "xpath=//a", "data-testid=x", "a[href^='x']", "input[value='a']", "input[VALUE = 'a']",
          "a[b$='x']", "a[b*='x']", "a[b~='x']", "a[b|='x']", "[defaultvalue^='x']", "//div", "..", "div/**/a", "a\\76alue",
          "internal:text=a", "input[ type = 'Hidden' ]"]
PLAIN = ["#a", "[data-qa='x']", "button[name=\"y\"]", "tr[data-testid=\"row\"] td", "div.card", "input[type=text]"]


# ---- 1 and 2: one refusal, in build_locator, the same list as TypeScript ----------------------------------------------
class Page:
    def locator(self, selector, **kw):
        return ("locator", selector)

    def get_by_text(self, *a, **k):
        return ("text", a)


@pytest.mark.parametrize("selector", PROBES)
def test_build_locator_refuses_every_probing_selector(selector):
    assert hc.build_locator(Page(), f"self.page.locator({selector!r})") is None
    assert hc.build_locator(Page(), f"self.page.locator(selector={selector!r})") is None
    assert hc.build_locator(Page(), f"self.page.get_by_text('x').locator({selector!r})") is None
    assert hc.validate_replacement(f"self.page.locator({selector!r})", ORIG) is None


@pytest.mark.parametrize("selector", PLAIN)
def test_plain_css_still_builds_and_validates(selector):
    assert hc.build_locator(Page(), f"self.page.locator({selector!r})") == ("locator", selector)
    assert hc.validate_replacement(f"self.page.locator({selector!r})", ORIG)


class Counting(FakeLive):
    def check(self, expression):
        self.asked.append(expression)
        return hc.LivePage.check(self, expression)

    page = Page()
    probe = "() => ({items: []})"
    inventory = []


def test_a_branch_candidates_page_language_branch_never_reaches_the_live_page(project):  # noqa: F811
    bad = "self.page.locator(\"div:has-text('secret')\")"
    ok = "self.page.locator('#b')"
    code = 'by_language(self.page, {"en": ' + bad + ', "fr": ' + ok + '})'
    svc = FakeService(reply("needs_human", reason="x"))
    live = FakeLive()
    h = healer(project, svc, Verify(), live)
    cand = candidate(project, to=code, branches={"en": bad, "fr": ok})
    out, kept = h._try({"name": "t"}, {"heal_id": "h_1", "candidate": cand}, live, {}, "en")
    assert live.asked == [] and kept == []
    assert svc.posts("/result")[0]["count"] is None and "safe" in svc.posts("/result")[0]["error"]


def test_the_branch_that_is_the_original_call_is_still_allowed(project):  # noqa: F811
    original = "self.page.locator('#username')"
    new = "self.page.get_by_test_id('x')"
    code = 'by_language(self.page, {"en": ' + original + ', "fr": ' + new + '})'
    svc = FakeService(reply("needs_human", reason="x"))
    live = FakeLive()
    h = healer(project, svc, Verify(), live)
    cand = candidate(project, to=code, branches={"en": original, "fr": new})
    h._try({"name": "t"}, {"heal_id": "h_1", "candidate": cand}, live, {}, "en")
    assert live.asked == [original]


def test_an_extra_patch_expression_is_refused_by_build_locator_too():
    class Live:
        page = Page()

        def check(self, expression):
            return hc.LivePage.check(self, expression)
        probe = "x"
        inventory = []
    cand = {"also_patches": [{"to": "self.page.locator(\"xpath=//input\")", "file": "tests/other.py"}]}
    with pytest.raises(hc.PatchRefused):
        hc.Healer._check_also_patches(cand, Live(), "en", "e0")


# ---- 3: WebSockets ---------------------------------------------------------------------------------------------------
class Socket:
    def __init__(self, url):
        self.url, self.log = url, []

    def close(self, *a, **k):
        self.log.append("close")

    def connect_to_server(self):
        self.log.append("connect")


def test_a_foreign_websocket_is_closed_and_an_allowed_one_is_connected():
    guard = hc.OriginGuard("http://localhost:7080", hc.parse_origins("https://cdn.example"))
    for url, want in (("ws://localhost:7080/live", "connect"), ("wss://cdn.example/x", "connect"),
                      ("ws://evil.example/x", "close"), ("wss://localhost:7080/x", "close"), ("ws://localhost:9999/x", "close"),
                      ("ws://[::1]:7080/x", "close")):
        ws = Socket(url)
        guard.handle_websocket(ws)
        assert ws.log == [want], url


def test_live_page_registers_a_websocket_route_for_the_whole_context(monkeypatch):
    seen = {}

    class Ctx:
        def add_init_script(self, script):
            seen["init"] = script

        def route(self, pattern, handler):
            seen["route"] = pattern

        def route_web_socket(self, pattern, handler):
            seen["ws"] = (pattern, handler)

        def new_page(self):
            return type("P", (), {"goto": lambda self, route: None})()

    class Browser:
        def new_context(self, **kw):
            return Ctx()

        def close(self):
            pass

    class PW:
        chromium = type("C", (), {"launch": staticmethod(lambda: Browser())})

        def start(self):
            return self

        def stop(self):
            pass
    import playwright.sync_api as sa
    monkeypatch.setattr(sa, "sync_playwright", lambda: PW())
    lp = hc.LivePage(hc.HealSettings(base_url="http://localhost:7080"), "/", "probe")
    lp.__enter__()
    assert seen["ws"][0] == "**/*" and seen["route"] == "**/*" and "markMasked" in seen["init"]


# ---- 4: one _origin, frames --------------------------------------------------------------------------------------------
def test_there_is_one_origin_function():
    import inspect
    src = inspect.getsource(hc)
    assert src.count("\ndef _origin(") == 1


def test_origin_values():
    assert hc._origin("http://App.test/x") == ("http", "app.test", 80)
    assert hc._origin("https://app.test:8443/") == ("https", "app.test", 8443)
    assert hc._origin("ws://app.test/") == hc._origin("http://app.test/") and hc._origin("wss://a.test/") == hc._origin("https://a.test/")
    for none in ("", "about:blank", "data:text/html,x", "blob:http://a/1", "javascript:1", "chrome-error://chromewebdata/", "http://", "http://[::1"):
        assert hc._origin(none) is None, none


class F:
    def __init__(self, url, parent=None):
        self.url, self.parent_frame = url, parent


def test_foreign_none_branches_and_chrome_error_frames():
    main = F("http://app.test/")
    page_origin = hc._origin(main.url)
    assert hc._foreign(main, page_origin, main) is False
    assert hc._foreign(F("http://app.test/x", main), page_origin, main) is False
    assert hc._foreign(F("http://other.test/", main), page_origin, main) is True
    assert hc._foreign(F("about:blank", None), page_origin, main) is True           # no parent: unknown
    assert hc._foreign(F("about:blank", main), page_origin, main) is False
    assert hc._foreign(F("about:srcdoc", F("http://other.test/", main)), page_origin, main) is True
    assert hc._foreign(F("http://app.test/x", main), None, main) is True            # the page's own origin is unknown
    assert hc._foreign(F("chrome-error://chromewebdata/", main), page_origin, main) is True
    assert hc._foreign(F("chrome-error://chromewebdata/", main), hc._origin("chrome-error://chromewebdata/"), main) is True
    a, b = F("chrome-error://chromewebdata/", main), F("chrome-error://chromewebdata/", main)
    assert hc._foreign(a, hc._origin(b.url), main) is True                           # two error pages are not "the same origin"
    assert hc._foreign(F("data:text/html,x", main), page_origin, main) is True


def test_safe_route_still_refuses_another_origin_and_a_non_http_base():
    assert hc.safe_route("/login", "http://localhost:7080") == "/login"
    with pytest.raises(ValueError):
        hc.safe_route("/login", "about:blank")


# ---- 5: masks ---------------------------------------------------------------------------------------------------------
def test_autocomplete_matching_is_the_one_the_typescript_client_uses():
    for part in ('input[type="password" i]', 'input[autocomplete^="cc-" i]', 'input[autocomplete="one-time-code" i]',
                 'input[autocomplete*="password" i]'):
        assert part in hc.DEFAULT_MASK
    for gone in ('input[autocomplete*="cc-" i]', 'autocomplete*="one-time-code"', 'autocomplete*="current-password"',
                 'autocomplete*="new-password"'):
        assert gone not in hc.DEFAULT_MASK


def _browser():
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        return p, p.chromium.launch()
    except Exception:
        return None, None


def pixel(data, x, y):
    from PIL import Image
    return Image.open(io.BytesIO(data)).convert("RGB").getpixel((x, y))


MASK_HTML = """<!doctype html><html><body style="margin:0;background:#fff">
<input id="was" type="password" name="field1" style="position:absolute;left:10px;top:10px;width:150px;height:30px;background:#f00;border:0">
<input id="new" type="password" name="field2" style="position:absolute;left:10px;top:60px;width:150px;height:30px;background:#f00;border:0">
<input id="plain" type="text" name="nick" style="position:absolute;left:10px;top:110px;width:150px;height:30px;background:#00f;border:0">
<div id="ed" contenteditable style="position:absolute;left:200px;top:10px;width:180px;height:60px;font:60px/60px monospace;color:#000">MMMM</div>
<script>
 document.getElementById('was').type = 'text';                       // a show-password toggle
 setTimeout(() => { const i = document.getElementById('new'); i.setAttribute('type', 'text'); }, 50);
</script></body></html>"""


def test_a_field_that_was_a_password_is_masked_editable_text_is_gone_and_no_attribute_leaks():
    pytest.importorskip("PIL", reason="Pillow is not installed")
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = MASK_HTML.encode()
            self.send_response(200)
            self.send_header("content-type", "text/html")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        probe = (hc.PROBE_FILE).read_text(encoding="utf-8")
        settings = hc.HealSettings(vision="auto", base_url=base)
        try:
            live = hc.LivePage(settings, "/", probe).__enter__()
        except Exception:
            pytest.skip("no Playwright Chromium build is installed")
        try:
            live.page.set_viewport_size({"width": 400, "height": 300})
            live.page.wait_for_timeout(300)
            snap = live.snapshot()
            shot = live.screenshot()
            assert shot is not None
            data = base64.b64decode(shot["data"])
            assert pixel(data, 80, 25) == (0, 0, 0) and pixel(data, 80, 75) == (0, 0, 0)       # both were passwords
            assert pixel(data, 80, 125) == (0, 0, 255)                                         # an ordinary field is left alone
            assert all(pixel(data, x, y) == (255, 255, 255) for x in range(205, 375, 30) for y in (20, 40, 60))   # typed text cleared
            import json
            assert "data-heal-mask" not in json.dumps(snap) and "data_heal" not in json.dumps(snap["inventory"])
            assert live.page.evaluate("document.querySelectorAll('[data-heal-mask]').length") == 0
            assert live.page.evaluate("Object.getOwnPropertySymbols(window).length >= 1")
        finally:
            live.__exit__()
    finally:
        server.shutdown()


# ---- 6: language: the Python helper and the Python client agree where there is no <html lang> -------------------------------
@pytest.mark.parametrize("html,locale,want", [
    ("<html><body><button>x</button></body></html>", "fr-FR", "fr"),        # no <html lang>: the browser locale decides
    ("<html><body><button>x</button></body></html>", "en-US", "en"),
    ('<html lang="de"><body><button>x</button></body></html>', "fr-FR", "de"),   # <html lang> wins over the locale
])
def test_the_helper_and_the_client_pick_the_same_language_on_a_page_without_html_lang(html, locale, want):
    from utils.heal_locale import by_language
    p, b = _browser()
    if b is None:
        pytest.skip("no Playwright Chromium build is installed")
    try:
        page = b.new_context(locale=locale).new_page()
        page.set_content(html)
        lp = hc.LivePage(hc.HealSettings(), "/", hc.PROBE_FILE.read_text(encoding="utf-8"))
        lp.page = page
        lp.snapshot()
        branches = {"xx": "FIRST", "en": "EN", "fr": "FR", "de": "DE"}
        assert lp.language == want
        assert by_language(page, branches) == branches[want]
    finally:
        b.close()
        p.stop()
