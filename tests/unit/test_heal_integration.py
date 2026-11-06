"""
===============================================================================
Integration Test: the real heal service, in process, against a real browser
===============================================================================
Starts the heal service's own app (FastAPI, the same HealSession core, a store that lives in memory) and drives the client
through it: the probe is fetched from the service and run in Chromium on a local page, the last green run's fingerprint
settles the element with no model call, the candidate is checked in the live page (one match, the right element), the patch
is applied to a temp project, and the French page gets a by_language branch that the shipped helper reads. The only model is
a stub that answers a pick from the candidate list the service sends it (no network, no model endpoint). The service is NOT a dependency of this repository: the test is skipped when heal-service (or a Chromium build) is not
installed. To run it locally:  pip install -e <path to heal-service>

Author: PMAC
===============================================================================
"""
import functools
import http.server
import re
import threading
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="heal-service is not installed (pip install -e <heal-service checkout>)")
pytest.importorskip("heal_service", reason="heal-service is not installed (pip install -e <heal-service checkout>)")

from fastapi.testclient import TestClient  # noqa: E402
from heal_service.app import create_app  # noqa: E402
from heal_service.config import ServiceSettings  # noqa: E402
from heal_service.core import HealSession  # noqa: E402
from heal_service.llm import Endpoint, Usage  # noqa: E402
from heal_service.store import Store  # noqa: E402
from heal_service.transport import CallResult  # noqa: E402

from utils import heal_fingerprints as fp  # noqa: E402
from utils.heal_client import HealSettings, Healer, ServiceClient  # noqa: E402
from utils.heal_locale import by_language  # noqa: E402


def _chromium_available():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _chromium_available(), reason="no Playwright Chromium build is installed")

LOGIN_EN = ('<html lang="en"><body><form><label for="u">Username</label>'
            '<input id="u" name="user" data-testid="login-user"><button type="submit">Log in</button></form></body></html>')
LOGIN_FR = ('<html lang="fr"><body><form><div>Connexion</div>'
            '<button type="submit">Valider</button></form></body></html>')
PAGE_PY = (
    "class LoginPage:\n"
    "    def __init__(self, page):\n"
    "        self.page = page\n"
    '        self.url = f"{BASE_URL}/login.html"\n'
    "\n"
    "    async def login(self, user):\n"
    "        await self.page.locator('#username').fill(user)\n"
)
BUTTON_PY = PAGE_PY.replace("#username').fill(user)", "#login-button').click()")
FILL_LINE = "await self.page.locator('#username').fill(user)"
CLICK_LINE = "await self.page.locator('#login-button').click()"


def error_for(line_no, locator):
    return (f"tests/test_login.py:2: in test_login\n    await LoginPage(page).login('u')\n"
            f"pages/login_page.py:{line_no}: in login\n    ...\nE   TimeoutError: waiting for locator('{locator}')\n")


@pytest.fixture
def site(tmp_path):
    """A static site on localhost that serves login.html from tmp_path/www."""
    www = tmp_path / "www"
    www.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(www))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield www, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


class StubModel:
    """Answers the service's pick: the listed element whose line holds `wanted` (usage is fixed: 100 in, 8 out)."""

    def __init__(self, wanted=None):
        self.wanted, self.calls = wanted, 0

    def call(self, ep, prompt, images=(), heal_id=""):
        self.calls += 1
        m = re.search(r"^(e\d+) \|.*" + re.escape(self.wanted or "\0"), prompt, re.M) if self.wanted else None
        text = '{"ref": "%s", "why": "the listed button"}' % m.group(1) if m else None
        return CallResult(text, "" if text else "no pick", Usage(100, 8), 5, True)


@pytest.fixture
def make_service():
    """A factory: the service's own app on a stub model (or none), the client wired to it in process."""
    opened = []

    def build(model=None):
        core = HealSession(ServiceSettings(), Store(":memory:", 14), model,
                           Endpoint(base_url="http://localhost:11434/v1", model="test-model") if model else None)
        http = TestClient(create_app(core))
        opened.append(http)
        return ServiceClient("http://testserver", "", http), core
    yield build
    for http in opened:
        http.close()


@pytest.fixture
def service(make_service):
    return make_service()


def project(tmp_path, source=PAGE_PY):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pages").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pages" / "login_page.py").write_text(source)
    (tmp_path / "tests" / "test_login.py").write_text("async def test_login(page):\n    await LoginPage(page).login('u')\n")
    return tmp_path


def healer(root, base_url, client, verify=lambda test: True):
    return Healer(client, HealSettings(url="http://testserver", base_url=base_url), verify, root=root, run_id="it1")


def test_fingerprint_heal_rewrites_the_locator_with_no_model_call(tmp_path, site, service):
    www, base = site
    (www / "login.html").write_text(LOGIN_EN)
    root = project(tmp_path / "proj")
    line = 7
    fp.merge_into(root, {fp.call_key("pages/login_page.py", FILL_LINE): {
        "file": "pages/login_page.py", "text": FILL_LINE, "page": "/login.html", "language": "en",
        "fingerprint": {"tag": "input", "attrs": {"id": "username", "name": "user"}}}}, env={})
    client, core = service
    d = healer(root, base, client).heal({"name": "test_login", "classname": "tests.test_login", "error": error_for(line, "#username")})
    assert d["outcome"] == "healed", d
    assert d["settled_at"] == 2 and d["usage"]["calls"] == 0 and d["usage"]["input_tokens"] == 0
    new = (root / "pages" / "login_page.py").read_text()
    assert "self.page.get_by_test_id(\"login-user\").fill(user)" in new and "#username" not in new
    rec = core.get(d["heal_id"])
    assert rec["outcome"] == "healed" and rec["verify_count"] == 1 and rec["verify_ref"]


def test_no_fingerprint_and_no_model_ends_needs_human_without_touching_the_file(tmp_path, site, service):
    www, base = site
    (www / "login.html").write_text(LOGIN_EN)
    root = project(tmp_path / "proj")
    client, _ = service
    d = healer(root, base, client).heal({"name": "test_login", "classname": "tests.test_login", "error": error_for(7, "#username")})
    assert d["outcome"] == "needs_human" and d["reason"] == "model_not_configured"
    assert (root / "pages" / "login_page.py").read_text() == PAGE_PY


def test_french_page_gets_a_by_language_branch_the_helper_reads(tmp_path, site, make_service):
    www, base = site
    (www / "login.html").write_text(LOGIN_FR)
    root = project(tmp_path / "proj", BUTTON_PY)
    # the passing run was in English: a submit button with the copy "Continue"; the page now reads French ("Valider"), a
    # translation that shares no word with the English. The service refuses a pick it cannot prove is the element the step
    # meant; here the page language changed (en -> fr), so the recorded box (the button's place) and its kind are the
    # proof, as a real fingerprint run records them.
    fp.merge_into(root, {fp.call_key("pages/login_page.py", CLICK_LINE): {
        "file": "pages/login_page.py", "text": CLICK_LINE, "page": "/login.html", "language": "en",
        "fingerprint": {"tag": "button", "type": "submit", "role": "button", "text": "Continue", "name": "Continue",
                        "box": {"x": 8, "y": 26, "w": 74, "h": 21}}}}, env={})
    model = StubModel(wanted="Valider")
    client, core = make_service(model)
    d = healer(root, base, client).heal({"name": "test_login", "classname": "tests.test_login", "error": error_for(7, "#login-button")})
    assert d["outcome"] == "healed", d
    assert model.calls == 1 and d["settled_at"] == 3 and d["usage"]["input_tokens"] == 100 and d["usage"]["output_tokens"] == 8
    new = (root / "pages" / "login_page.py").read_text()
    assert "by_language(self.page," in new and '"fr"' in new and '"en"' in new
    assert "Continue" in new and "Valider" in new              # copy is kept per language, never translated
    assert "from utils.heal_locale import by_language\n" in new
    compile(new, "login_page.py", "exec")                            # the edited page object is still valid Python
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:                                   # the shipped helper reads the page language
        b = p.chromium.launch()
        pg = b.new_page(base_url=base)
        pg.goto("/login.html")
        assert by_language(pg, {"en": "EN", "fr": "FR"}) == "FR"
        assert by_language(pg, {"de": "DE", "en": "EN"}) == "DE"
        b.close()
