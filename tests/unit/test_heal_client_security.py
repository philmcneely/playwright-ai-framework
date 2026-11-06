"""
===============================================================================
Unit Tests: heal client security findings (every service reply is untrusted input)
===============================================================================
One test per exploit, each written to fail before its fix: a typed value reaching the service, a trailing comment that
swallows the rest of a line, a span that covers more than a locator, a live check on code that is not the code written,
a probe script supplied by the service, a partial multi-file write, a symlink or a file mode lost on write, a bearer token
over plain http, fingerprint copy that may hold personal data, markdown injected through a PR body, a HEAL_DIR that leaves
the repository, and a helper import faked by a comment.

Author: PMAC
===============================================================================
"""
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path

import httpx
import pytest

from tests.unit.test_heal_client import (ERROR, FAILURE, FROM, PAGE_SRC, TO, FakeLive, FakeService, Verify, candidate,
                                         healer, patch_for, reply, sha)
from utils import heal_client as hc
from utils import heal_fingerprints as fp
from utils.heal_client import (HealServiceError, HealSettings, Healer, LivePage, PatchRefused, ServiceClient,
                               check_replacement, collect_source, plan_patches, validate_replacement, write_files)
from utils.heal_redact import clean_inventory, redact_typed_values

_SPEC = importlib.util.spec_from_file_location("heal_cli", Path(__file__).resolve().parents[2] / "scripts" / "heal.py")
heal_cli = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(heal_cli)

ORIGINAL = "page.locator('#a')"


@pytest.fixture
def project(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pages" / "login_page.py").write_text(PAGE_SRC)
    (tmp_path / "pages" / "other_page.py").write_text("x = self.page.locator('#username')\n")
    (tmp_path / "tests" / "test_login.py").write_text("async def test_valid_login(page):\n    pass\n")
    return tmp_path


# ---- HIGH-1: typed values never leave the client ---------------------------------------------------------------------
class TestTypedValues:
    def test_redacts_a_prefilled_password_and_nested_typed_text(self):
        aria = ('- textbox "Pw": hunter2\n- textbox "Email": me@example.com\n- searchbox "Find":\n  - text: secret query\n'
                '- spinbutton "Qty": 7\n- button "Go"\n- textbox "Note": |\n    line one\n    line two\n- link "Home"\n')
        out = redact_typed_values(aria)
        for leaked in ("hunter2", "me@example.com", "secret query", "line one", "line two"):
            assert leaked not in out
        assert '- textbox "Pw"' in out and '- button "Go"' in out and '- link "Home"' in out

    def test_hostile_text_is_linear(self):
        redact_typed_values('- textbox "' + 'a\\' * 200_000)         # an unterminated key must not blow up

    def test_the_request_carries_no_typed_value_even_when_the_page_snapshot_does(self, project):
        svc = FakeService(reply("not_drift"))
        live = FakeLive(inventory=[{"ref": "e0", "tag": "input", "value": "hunter2", "defaultValue": "hunter2",
                                    "innerHTML": "<b>hunter2</b>", "data_note": "ok", "data_csrf_token": "t0k",
                                    "data_value": "v", "id": "pw", "box": {"x": 1, "y": 2, "width": 3, "height": 4}}])
        live.snapshot = lambda: {"path": "/login", "inventory": live.inventory, "more": 0,
                                 "aria": '- textbox "Pw": hunter2\n- button "Go"\n',
                                 "viewport": {"w": 1, "h": 1, "dpr": 1}, "language": {"html_lang": "en"}}
        healer(project, svc, Verify(), live).heal(FAILURE)
        raw = json.dumps(svc.posts("/v1/heal")[0])
        assert "hunter2" not in raw and "t0k" not in raw and "innerHTML" not in raw and "defaultValue" not in raw
        item = svc.posts("/v1/heal")[0]["page"]["inventory"][0]
        assert item == {"ref": "e0", "tag": "input", "data_note": "ok", "id": "pw",
                        "box": {"x": 1, "y": 2, "width": 3, "height": 4}}

    def test_allowlist_drops_unknown_keys_values_and_non_plain_types(self):
        out = clean_inventory([{"tag": "a", "text": "Go", "value": "x", "Value": "x", "defaultValue": "x", "custom": "x",
                                "name": {"nested": "x"}, "disabled": True, "box": {"x": "1"}}, "junk", None])
        assert out == [{"tag": "a", "text": "Go", "disabled": True}]
        assert clean_inventory("not a list") == []

    def test_the_live_page_redacts_its_own_snapshot(self):
        class Body:
            def aria_snapshot(self):
                return '- textbox "Pw": hunter2\n'

        class Pg:
            url = "http://localhost:7080/login?token=abc"

            def evaluate(self, script):
                return {"items": [{"tag": "input", "value": "hunter2"}], "more": 0, "page": {"lang": "en"}}

            def locator(self, sel):
                return Body()
        live = LivePage(HealSettings(), "/login", "probe")
        live.page, live._response = Pg(), None
        snap = live.snapshot()
        assert "hunter2" not in json.dumps(snap) and snap["inventory"] == [{"ref": "e0", "tag": "input"}]


# ---- HIGH-2: a comment or control character cannot swallow the rest of a line ------------------------------------------
class TestCommentsAndControls:
    @pytest.mark.parametrize("to", [
        'page.locator("#b")  # ',
        'page.locator("#b")#',
        'page.locator("#b") # .fill("x")',
        'page.locator("#b")\r',
        'page.locator("#b")\x0c',
        'page.locator("#b")\x0b',
        'page.locator("#b")\x00',
        'page.locator("#b")\t',
        'page.locator("#b")\u202e',
        'page.locator("#b")\u2028',
        'page.locator("#b")\x85',
        'page.locator("#b"\r)',
        'page.locator("#\x0cb")',
    ])
    def test_both_validators_reject_them(self, to):
        assert validate_replacement(to, ORIGINAL) is None
        assert check_replacement(to, ORIGINAL) is not None

    def test_a_branch_with_a_comment_is_refused(self):
        br = {"en": "page.get_by_label('A')", "fr": "page.get_by_label('B')"}
        to = 'by_language(page, {"en": page.get_by_label(\'A\'), "fr": page.get_by_label(\'B\')})  # '
        assert check_replacement(to, ORIGINAL, br) is not None

    @pytest.mark.parametrize("ok", ["page.locator('#b')", 'page.locator("#b")', "page.get_by_role('button', name='Go').first"])
    def test_ordinary_locators_still_pass(self, ok):
        assert validate_replacement(ok, ORIGINAL) == ok

    def test_a_comment_cannot_reach_the_file(self, project):
        bad = FROM + "  # "
        svc = FakeService(reply("try", candidate(project, to=bad)), reply("needs_human", reason="x"))
        verify = Verify(root=project)
        healer(project, svc, verify).heal(FAILURE)
        assert (project / "pages/login_page.py").read_text() == PAGE_SRC and verify.calls == 0


# ---- HIGH-3: the original must be a locator chain and an AST node of the file -----------------------------------------
class TestOriginalSpan:
    def test_from_that_covers_more_than_a_locator_is_refused(self):
        assert check_replacement("page.locator('#b')", "page.locator('#a').click()") is not None

    def test_a_span_that_covers_a_click_is_refused_and_nothing_is_written(self, project):
        frm = "self.page.locator('#username').fill(user)"
        cand = candidate(project, frm=frm)
        svc = FakeService(reply("try", cand), reply("needs_human", reason="x"))
        verify = Verify(root=project)
        healer(project, svc, verify).heal(FAILURE)
        assert (project / "pages/login_page.py").read_text() == PAGE_SRC and verify.calls == 0

    def test_a_span_inside_a_string_or_comment_is_not_a_node(self, project):
        text = "# self.page.locator('#username')\nx = \"self.page.locator('#username')\"\n"
        (project / "pages" / "login_page.py").write_text(text)
        for nth in (0, 1):
            cand = candidate(project, nth=nth)
            with pytest.raises(PatchRefused) as e:
                plan_patches(cand, {"pages/login_page.py": sha(text)}, ("pages",), project)
            assert e.value.fatal and "syntax" in e.value.reason

    def test_a_span_that_cuts_a_node_in_half_is_refused(self, project):
        frm = "self.page.locator("
        cand = candidate(project, frm=frm)
        with pytest.raises(PatchRefused):
            plan_patches(cand, {"pages/login_page.py": sha(PAGE_SRC)}, ("pages",), project)

    def test_a_file_that_does_not_parse_is_refused(self, project):
        text = "def broken(:\n    self.page.locator('#username')\n"
        (project / "pages" / "login_page.py").write_text(text)
        with pytest.raises(PatchRefused):
            plan_patches(candidate(project), {"pages/login_page.py": sha(text)}, ("pages",), project)

    def test_the_real_node_is_accepted(self, project):
        planned = plan_patches(candidate(project), {"pages/login_page.py": sha(PAGE_SRC)}, ("pages",), project)
        assert TO in planned[0].new_text


# ---- HIGH-4: the code that was checked live is the code that is written -------------------------------------------------
class TestCheckedIsWritten:
    def test_a_patch_whose_to_differs_from_the_checked_code_is_refused(self, project):
        cand = candidate(project)
        cand["patch"]["to"] = "self.page.get_by_test_id('something-else')"          # a safe locator, but not the checked one
        svc = FakeService(reply("try", cand), reply("needs_human", reason="x"))
        live, verify = FakeLive(), Verify(root=project)
        d = healer(project, svc, verify, live).heal(FAILURE)
        assert (project / "pages/login_page.py").read_text() == PAGE_SRC and verify.calls == 0
        assert d["outcome"] == "needs_human"

    def test_quote_style_and_spacing_do_not_count_as_a_difference(self, project):
        cand = candidate(project)
        cand["code"] = 'self.page.get_by_test_id( "login-user" )'
        planned = plan_patches(cand, {"pages/login_page.py": sha(PAGE_SRC)}, ("pages",), project)
        assert TO in planned[0].new_text

    def test_an_also_patch_that_hits_two_elements_refuses_the_whole_candidate(self, project):
        also = [patch_for(project, "self.page.get_by_text('Everything')", file="pages/other_page.py")]
        svc = FakeService(reply("try", candidate(project, also=also)), reply("needs_human", reason="x"))
        live = FakeLive({"self.page.get_by_text('Everything')": (2, None)})
        verify = Verify(root=project)
        healer(project, svc, verify, live).heal({**FAILURE, "error": ERROR + "pages/other_page.py:1: in z\n"})
        assert (project / "pages/login_page.py").read_text() == PAGE_SRC and verify.calls == 0
        assert (project / "pages/other_page.py").read_text() == "x = self.page.locator('#username')\n"

    def test_an_also_patch_that_hits_another_element_refuses_the_whole_candidate(self, project):
        also = [patch_for(project, "self.page.get_by_text('Other')", file="pages/other_page.py")]
        svc = FakeService(reply("try", candidate(project, also=also)), reply("needs_human", reason="x"))
        live = FakeLive({"self.page.get_by_text('Other')": (1, "e9")})
        verify = Verify(root=project)
        healer(project, svc, verify, live).heal({**FAILURE, "error": ERROR + "pages/other_page.py:1: in z\n"})
        assert verify.calls == 0 and (project / "pages/login_page.py").read_text() == PAGE_SRC

    def test_every_also_patch_is_checked_live(self, project):
        also = [patch_for(project, TO, nth=1), patch_for(project, TO, file="pages/other_page.py")]
        cand = candidate(project, also=also)
        svc = FakeService(reply("try", cand), reply("healed", cand))
        live = FakeLive()
        healer(project, svc, Verify(True, root=project), live).heal({**FAILURE, "error": ERROR + "pages/other_page.py:1: in z\n"})
        assert live.asked == [TO, TO, TO]

    def test_branch_also_patch_is_checked_in_the_page_language(self, project):
        br = {"en": "self.page.get_by_label('Username')", "fr": "self.page.get_by_label('Nom')"}
        to = 'by_language(self.page, {"en": ' + br["en"] + ', "fr": ' + br["fr"] + "})"
        cand = candidate(project, to=to, branches=br, also=[patch_for(project, to, nth=1)])
        svc = FakeService(reply("try", cand), reply("healed", cand))
        live = FakeLive(language="fr")
        healer(project, svc, Verify(True, root=project), live).heal(FAILURE)
        assert live.asked == [br["fr"], br["fr"]]

    def test_a_branch_that_differs_from_what_was_checked_is_refused(self, project):
        br = {"en": "self.page.get_by_label('Username')", "fr": "self.page.get_by_label('Nom')"}
        to = 'by_language(self.page, {"en": ' + br["en"] + ', "fr": self.page.get_by_label(\'Evil\')})'
        assert "differs" in check_replacement(to, FROM, br)


# ---- HIGH-5: the probe is vendored; a service copy must be byte-identical; foreign origins are blocked ------------------
class TestProbe:
    def vendored(self):
        return Path(hc.__file__).with_name("heal_probe.js").read_text(encoding="utf-8")

    def test_the_vendored_probe_is_used_and_the_service_is_not_asked(self):
        svc = FakeService()
        assert svc.client().probe_js() == self.vendored()
        assert not [r for r in svc.requests if r[1] == "/v1/probe.js"]

    def test_the_vendored_probe_never_reads_a_value(self):
        text = self.vendored()
        assert "el.value" in text and "textarea" in text            # the one place a value is read is a button's own label

    def test_service_probe_with_other_bytes_is_refused(self):
        svc = FakeService()                                          # serves a different script at /v1/probe.js
        client = ServiceClient("http://svc", "", httpx.Client(transport=httpx.MockTransport(svc.handler)),
                               env={"HEAL_PROBE_FROM_SERVICE": "1"})
        with pytest.raises(HealServiceError, match="probe"):
            client.probe_js()

    def test_service_probe_with_identical_bytes_is_accepted(self):
        text = self.vendored()
        client = ServiceClient("http://svc", "", httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, text=text))), env={"HEAL_PROBE_FROM_SERVICE": "1"})
        assert hashlib.sha256(client.probe_js().encode()).hexdigest() == hashlib.sha256(text.encode()).hexdigest()

    def test_foreign_origins_are_blocked_only_while_probing(self):
        guard = hc.OriginGuard("http://localhost:7080")
        calls = []

        class Route:
            def __init__(self, url):
                self.request = type("R", (), {"url": url})()

            def abort(self):
                calls.append(("abort", self.request.url))

            def continue_(self):
                calls.append(("continue", self.request.url))
        guard.handle(Route("http://evil.example/x.png"))
        guard.probing = True
        guard.handle(Route("http://evil.example/x.png"))
        guard.handle(Route("http://localhost:7080/app.js"))
        guard.handle(Route("http://localhost:9999/app.js"))
        guard.handle(Route("data:text/plain,hi"))
        assert calls == [("continue", "http://evil.example/x.png"), ("abort", "http://evil.example/x.png"),
                         ("continue", "http://localhost:7080/app.js"), ("abort", "http://localhost:9999/app.js"),
                         ("continue", "data:text/plain,hi")]

    def test_snapshot_and_check_run_the_probe_with_the_guard_on(self):
        seen = []
        live = LivePage(HealSettings(), "/", "probe")
        live.guard = hc.OriginGuard("http://localhost:7080")

        class Body:
            def aria_snapshot(self):
                seen.append(("aria", live.guard.probing))
                return ""

        class Pg:
            url = "http://localhost:7080/"

            def evaluate(self, script):
                seen.append(("evaluate", live.guard.probing))
                return {"items": [], "more": 0, "page": {}}

            def locator(self, sel):
                return Body()
        live.page, live._response = Pg(), None
        live.snapshot()
        assert ("evaluate", True) in seen and live.guard.probing is False


# ---- MEDIUM -----------------------------------------------------------------------------------------------------------
class TestWrites:
    def test_a_partial_multi_file_write_is_reverted(self, project, monkeypatch):
        also = [patch_for(project, TO, file="pages/other_page.py")]
        cand = candidate(project, also=also)
        svc = FakeService(reply("try", cand), reply("needs_human", reason="x"))
        real, count = hc._replace, {"n": 0}

        def flaky(path, data):
            count["n"] += 1
            if count["n"] == 2:
                raise OSError("disk full")
            real(path, data)
        monkeypatch.setattr(hc, "_replace", flaky)
        d = healer(project, svc, Verify(root=project)).heal({**FAILURE, "error": ERROR + "pages/other_page.py:1: in z\n"})
        assert (project / "pages/login_page.py").read_text() == PAGE_SRC
        assert (project / "pages/other_page.py").read_text() == "x = self.page.locator('#username')\n"
        assert d["reason"] == "client_error"

    def test_file_mode_survives_a_write_and_a_revert(self, project):
        path = project / "pages" / "login_page.py"
        path.chmod(0o750)
        planned = plan_patches(candidate(project), {"pages/login_page.py": sha(PAGE_SRC)}, ("pages",), project)
        write_files(project, planned)
        assert stat.S_IMODE(path.stat().st_mode) == 0o750 and TO in path.read_text()
        hc.revert_files(project, planned)
        assert stat.S_IMODE(path.stat().st_mode) == 0o750 and path.read_text() == PAGE_SRC

    def test_writing_through_a_symlink_is_refused(self, project):
        target = project / "conftest.py"
        target.write_text("x = 1\n")
        link = project / "pages" / "link.py"
        link.symlink_to(target)
        planned = [hc.PlannedFile("pages/link.py", b"x = 1\n", "x = 2\n")]
        with pytest.raises(OSError):
            write_files(project, planned)
        assert target.read_text() == "x = 1\n" and link.is_symlink()

    def test_a_symlinked_file_inside_the_repo_but_outside_the_roots_is_not_planned(self, project):
        target = project / "conftest.py"
        target.write_text("x = self.page.locator('#username')\n")
        (project / "pages" / "link.py").symlink_to(target)
        text = target.read_text()
        cand = candidate(project, file="pages/link.py")
        with pytest.raises(PatchRefused) as e:
            plan_patches(cand, {"pages/link.py": sha(text)}, ("pages",), project)
        assert e.value.fatal

    def test_collect_source_checks_each_source_root(self, project):
        (project / "conftest.py").write_text("SECRET = 1\n")
        (project / "pages" / "link.py").symlink_to(project / "conftest.py")           # resolves inside the repo
        stack = [{"file": "pages/link.py", "line": 1}, {"file": "pages/login_page.py", "line": 1}]
        assert [f["path"] for f in collect_source(stack, ("pages",), project)] == ["pages/login_page.py"]

    def test_collect_source_skips_a_symlinked_directory_that_leaves_the_root(self, project):
        (project / "tests" / "x.py").write_text("y = 1\n")
        (project / "pages" / "d").symlink_to(project / "tests")
        assert collect_source([{"file": "pages/d/x.py", "line": 1}], ("pages",), project) == []


class TestBearerOverHttp:
    def call(self, url, token="tok", env=None):
        client = ServiceClient(url, token, httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"ok": True}))), env=env or {})
        return client.capabilities()

    def test_a_token_over_http_to_a_remote_host_is_refused_with_a_warning(self):
        with pytest.warns(UserWarning, match="HEAL_ALLOW_INSECURE"), pytest.raises(HealServiceError, match="http"):
            self.call("http://heal.example.test:8765")

    @pytest.mark.parametrize("url", ["http://localhost:8765", "http://127.0.0.1:8765", "http://[::1]:8765",
                                     "https://heal.example.test"])
    def test_localhost_and_https_are_fine(self, url):
        assert self.call(url) == {"ok": True}

    def test_no_token_means_no_refusal(self):
        assert self.call("http://heal.example.test", token="") == {"ok": True}

    def test_the_override_allows_it(self):
        assert self.call("http://heal.example.test", env={"HEAL_ALLOW_INSECURE": "1"}) == {"ok": True}


class TestFingerprintCopy:
    ITEM = {"tag": "button", "role": "button", "name": "Jane Doe", "label": "Jane", "text": "Jane Doe", "row": "row-jane",
            "placeholder": "Jane", "aria_label": "Jane Doe", "title": "Jane", "id": "go", "testid": "go-btn"}

    def test_copy_is_stored_as_given_by_default(self):
        f = fp.item_to_fingerprint(self.ITEM)
        assert f["text"] == "Jane Doe" and f["row"] == "row-jane"

    def test_copy_off_stores_only_hashes_of_copy(self):
        f = fp.item_to_fingerprint(self.ITEM, copy="off")
        raw = json.dumps(f)
        assert "Jane" not in raw and "row-jane" not in raw
        assert f["text"] == f["name"] and f["text"].startswith("sha256:")
        assert f["tag"] == "button" and f["attrs"]["id"] == "go" and f["attrs"]["data-testid"] == "go-btn"
        again = fp.item_to_fingerprint({**self.ITEM, "text": "  jane   DOE "}, copy="off")
        assert again["text"] == f["text"]                      # whitespace and case do not change the hash

    def test_the_recorder_reads_the_switch_from_its_environment(self):
        assert fp.copy_mode({"HEAL_FINGERPRINT_COPY": "OFF"}) == "off"
        assert fp.copy_mode({}) == "on" and fp.copy_mode({"HEAL_FINGERPRINT_COPY": "maybe"}) == "on"


# ---- LOW ---------------------------------------------------------------------------------------------------------------
class TestLow:
    def test_pr_body_escapes_markdown_in_every_service_string(self):
        healed = [{"test": "test_[x](http://evil.example)", "from": "a`b", "to": "c", "why": "<img src=x> *bold*\n# Head",
                   "source": "s"}]
        other = [{"test": "t_@mention", "why": "[click](http://evil.example) ![i](x)\r\n- injected"}]
        body = heal_cli.build_pr_body(healed, other)
        assert "[x](http" not in body and "<img" not in body and "](http://evil" not in body
        assert "\n# Head" not in body and "\n- injected" not in body
        assert "\\[x\\]" in body and "&lt;img" in body

    def test_pr_commit_lines_are_single_lines(self):
        lines = heal_cli.commit_lines([{"test": "t\nCo-Authored-By: x", "from": "a", "to": "b"}])
        assert len(lines) == 1 and "\n" not in lines[0]

    @pytest.mark.parametrize("value", ["/etc", "../x", "a/../../x", "C:\\x", "~/x", "a\\b", ""])
    def test_heal_dir_must_be_a_relative_path_inside_the_repo(self, tmp_path, value):
        with pytest.warns(UserWarning):
            got = fp.heal_dir(tmp_path, {"HEAL_DIR": value or "  /"})
        assert got == tmp_path / ".heal"

    def test_heal_dir_that_resolves_outside_through_a_symlink_is_refused(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "cache").symlink_to(outside)
        with pytest.warns(UserWarning):
            assert fp.heal_dir(repo, {"HEAL_DIR": "cache"}) == repo / ".heal"

    def test_heal_dir_ok(self, tmp_path):
        assert fp.heal_dir(tmp_path, {"HEAL_DIR": "build/heal"}) == tmp_path / "build/heal"

    def test_the_healer_reads_the_validated_heal_dir(self, project, monkeypatch):
        monkeypatch.setenv("HEAL_DIR", "/etc")
        with pytest.warns(UserWarning):
            Healer(FakeService().client(), HealSettings(), Verify(), root=project)._last_pass(
                [{"file": "pages/login_page.py", "line": 10}])

    @pytest.mark.parametrize("raw", ["/etc", "/", "pages,/etc", "pages,../x", "pages,C:\\x", "pages\\x", "~/x"])
    def test_source_roots_must_be_relative_inside_the_repo(self, raw):
        assert fp.source_roots({"HEAL_SOURCE_ROOTS": raw}) == (("pages",) if raw.startswith("pages,") else
                                                                ("pages", "tests", "utils"))

    def test_source_roots_still_accept_nested_relative_roots(self):
        assert fp.source_roots({"HEAL_SOURCE_ROOTS": "src/pages, e2e/"}) == ("src/pages", "e2e")

    def test_helper_import_is_added_when_only_a_comment_or_string_mentions_it(self, project):
        text = ('# from utils.heal_locale import by_language\n"import by_language"\n\n'
                "class P:\n    def go(self):\n        return self.page.locator('#username')\n")
        (project / "pages" / "login_page.py").write_text(text)
        br = {"en": "self.page.get_by_label('U')", "fr": "self.page.get_by_label('N')"}
        to = 'by_language(self.page, {"en": ' + br["en"] + ', "fr": ' + br["fr"] + "})"
        cand = candidate(project, to=to, branches=br)
        new = plan_patches(cand, {"pages/login_page.py": sha(text)}, ("pages",), project)[0].new_text
        import ast
        real = [n for n in ast.parse(new).body if isinstance(n, ast.ImportFrom) and n.module == "utils.heal_locale"]
        assert len(real) == 1 and [a.name for a in real[0].names] == ["by_language"]

    def test_helper_import_is_not_duplicated_when_really_imported(self, project):
        text = ("from utils.heal_locale import by_language\n\nclass P:\n    def go(self):\n"
                "        return self.page.locator('#username')\n")
        (project / "pages" / "login_page.py").write_text(text)
        br = {"en": "self.page.get_by_label('U')", "fr": "self.page.get_by_label('N')"}
        to = 'by_language(self.page, {"en": ' + br["en"] + ', "fr": ' + br["fr"] + "})"
        new = plan_patches(candidate(project, to=to, branches=br), {"pages/login_page.py": sha(text)}, ("pages",),
                           project)[0].new_text
        assert new.count("import by_language") == 1


class TestHostileServiceJson:
    """A service reply nested deep enough to overflow the JSON parser is a bad reply, not a crash."""

    def _client(self, status, body):
        import httpx
        from utils.heal_client import ServiceClient
        transport = httpx.MockTransport(lambda request: httpx.Response(status, content=body))
        return ServiceClient("https://svc.example", token="t", http=httpx.Client(transport=transport))

    def test_a_deeply_nested_reply_raises_a_service_error(self):
        import pytest
        from utils.heal_client import HealServiceError
        deep = b"[" * 200000 + b"]" * 200000
        with pytest.raises(HealServiceError):
            self._client(200, deep).capabilities()

    def test_an_error_reply_that_is_deep_or_not_an_object_still_reports_the_status(self):
        import pytest
        from utils.heal_client import HealServiceError
        for body in (b"[" * 200000 + b"]" * 200000, b'["x"]'):
            with pytest.raises(HealServiceError, match="500"):
                self._client(500, body).capabilities()
