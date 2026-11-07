"""
===============================================================================
Unit Tests: utils/heal_fingerprints.py -- what a clean green run records for the heal service
===============================================================================
No browser: a fake locator answers the probe call. Covers the key (file + normalized acting line), the facts (never a
value), the atomic file with its `*` .gitignore and the opt-in to commit it, the neighbours of a page, the clean-green rule
(passed, no rerun, not flaky, not during a heal) and that nothing is recorded unless HEAL_FINGERPRINTS=on.

Author: PMAC
===============================================================================
"""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from utils import heal_fingerprints as fp

ITEM = {"tag": "input", "type": "text", "role": "", "name": "Username", "aria_label": "", "label": "Username",
        "placeholder": "", "id": "username", "testid": "login-user", "data_test": "", "data_qa": "u1", "data_cy": "",
        "class": "form-control", "name_attr": "user", "title": "", "alt": "", "text": "", "disabled": False, "hidden": False,
        "box": {"x": 410, "y": 218, "width": 280, "height": 36}, "row": "login-form", "data_section": "auth"}
PROBE = {"items": [ITEM], "more": 0, "page": {"path": "/login", "lang": "fr-CA", "browser_lang": "en-US"}}


class FakeLocator:
    def __init__(self, data=PROBE, frame=""):
        self.data, self.frame, self.calls = data, frame, []

    async def evaluate(self, script, timeout=None):
        self.calls.append(script)
        return self.data if "frameElement" not in script else self.frame


def item(name="t", outcomes=("passed", "passed", "passed"), execution_count=1, flaky=False):
    return SimpleNamespace(nodeid=f"tests/unit/x.py::{name}", execution_count=execution_count,
                           get_closest_marker=lambda m: object() if (flaky and m == "flaky") else None)


def recorder(tmp_path, **kw):
    return fp.Recorder(root=Path(__file__).resolve().parents[2], env=kw.pop("env", {"HEAL_DIR": "."}),
                       probe="(only) => 1", **kw)


class TestKeysAndFacts:
    def test_the_key_ignores_indentation_spacing_and_quote_style(self):
        a = fp.call_key("pages/p.py", "        await  self.page.locator(\"#u\").fill(v)  ")
        b = fp.call_key("pages/p.py", "await self.page.locator('#u').fill(v)")
        assert a == b == "pages/p.py::await self.page.locator('#u').fill(v)"

    def test_line_of_reads_the_normalized_line(self, tmp_path):
        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "p.py").write_text("a = 1\n    await self.page.locator(\"#u\").fill(v)\n")
        assert fp.line_of(tmp_path, "pages/p.py", 2) == "await self.page.locator('#u').fill(v)"
        assert fp.line_of(tmp_path, "pages/p.py", 9) == "" and fp.line_of(tmp_path, "pages/none.py", 1) == ""

    def test_fingerprint_facts_in_the_service_shape_and_never_a_value(self):
        out = fp.item_to_fingerprint(ITEM, "login-frame")
        assert out["tag"] == "input" and out["name"] == "Username" and out["label"] == "Username" and out["row"] == "login-form"
        assert out["attrs"] == {"data-testid": "login-user", "id": "username", "name": "user", "class": "form-control",
                                "data-qa": "u1", "data-section": "auth"}
        assert out["box"] == {"x": 410, "y": 218, "w": 280, "h": 36} and out["frame"] == "login-frame"
        assert "value" not in json.dumps(out).lower().replace("data-", "")
        assert "hidden" not in out and "disabled" not in out

    def test_a_hidden_element_has_no_box(self):
        assert "box" not in fp.item_to_fingerprint({**ITEM, "box": None})

    def test_page_path_drops_query_and_fragment(self):
        assert fp.page_path("https://app.example/login?token=abc#x") == "/login" and fp.page_path("") == "/"

    def test_relative_under_roots(self, tmp_path):
        roots = ("pages", "tests")
        assert fp.relative_under("pages/a.py", tmp_path, roots) == "pages/a.py"
        assert fp.relative_under(str(tmp_path / "tests" / "b.py"), tmp_path, roots) == "tests/b.py"
        for bad in ("conftest.py", "../pages/a.py", "/etc/pages/a.py", "pages/../x.py"):
            assert fp.relative_under(bad, tmp_path, roots) is None

    def test_roots_come_from_the_environment(self):
        assert fp.source_roots({}) == ("pages", "tests", "utils")
        assert fp.source_roots({"HEAL_SOURCE_ROOTS": "src/pages, e2e"}) == ("src/pages", "e2e")
        assert fp.source_roots({"HEAL_SOURCE_ROOTS": "../x"}) == ("pages", "tests", "utils")


class TestFile:
    def rec(self, text="a", page="/login", **fpr):
        return {"file": "pages/p.py", "text": text, "page": page, "language": "en", "fingerprint": {"tag": "input", **fpr}}

    def test_atomic_write_creates_the_file_and_a_star_gitignore(self, tmp_path):
        assert fp.merge_into(tmp_path, {"k": self.rec()}, env={}) is True
        assert json.loads((tmp_path / ".heal" / "fingerprints.json").read_text())["entries"]["k"]["page"] == "/login"
        assert (tmp_path / ".heal" / ".gitignore").read_text() == "*\n"
        assert not list((tmp_path / ".heal").glob("*.tmp"))

    def test_an_unchanged_merge_does_not_rewrite_the_file(self, tmp_path):
        fp.merge_into(tmp_path, {"k": self.rec()}, env={})
        target = tmp_path / ".heal" / "fingerprints.json"
        before = target.stat().st_mtime_ns
        assert fp.merge_into(tmp_path, {"k": self.rec()}, env={}) is False and target.stat().st_mtime_ns == before

    def test_merging_keeps_what_another_worker_wrote(self, tmp_path):
        fp.merge_into(tmp_path, {"a": self.rec("a")}, env={})
        fp.merge_into(tmp_path, {"b": self.rec("b")}, env={})
        assert set(fp.load_store(tmp_path / ".heal" / "fingerprints.json")["entries"]) == {"a", "b"}

    def test_committing_is_an_opt_in_and_then_no_ignore_file_is_written(self, tmp_path):
        fp.merge_into(tmp_path, {"k": self.rec()}, env={"HEAL_FINGERPRINTS_COMMIT": "on"})
        assert (tmp_path / ".heal" / "fingerprints.json").exists() and not (tmp_path / ".heal" / ".gitignore").exists()

    def test_a_corrupt_file_reads_as_empty(self, tmp_path):
        (tmp_path / "f.json").write_text("{nope")
        assert fp.load_store(tmp_path / "f.json") == {"version": 1, "entries": {}}

    def test_last_pass_has_the_fingerprint_the_language_and_same_page_neighbours_only(self):
        store = {"entries": {"k": self.rec("k", id="u"), "n1": self.rec("n1", id="p"), "n2": self.rec("n2", page="/other", id="z")}}
        lp = fp.last_pass_for(store, "k")
        assert lp["fingerprint"] == {"tag": "input", "id": "u"}
        assert lp["neighbours"] == [{"tag": "input", "id": "p"}] and lp["language"] == "en"
        assert fp.last_pass_for(store, "missing") is None

    def test_neighbours_are_capped_at_what_the_service_accepts(self):
        store = {"entries": {f"n{i:03}": self.rec(f"n{i}", id=str(i)) for i in range(150)}}
        store["entries"]["k"] = self.rec("k")
        assert len(fp.last_pass_for(store, "k")["neighbours"]) == 100


class TestRecording:
    def test_records_facts_box_frame_page_language_keyed_by_the_acting_line(self, tmp_path):
        r = recorder(tmp_path)
        r.start_test(item())
        asyncio.run(r.record(FakeLocator(frame="f1")))              # this line is the acting line
        (key, entry), = r.pending.items()
        assert key.startswith("tests/unit/test_heal_fingerprints.py::asyncio.run(r.record(FakeLocator(frame=")
        assert entry["page"] == "/login" and entry["language"] == "fr" and entry["file"].endswith("test_heal_fingerprints.py")
        assert entry["fingerprint"]["frame"] == "f1" and entry["fingerprint"]["box"]["w"] == 280

    def test_one_probe_per_acting_line_per_test(self, tmp_path):
        r, loc = recorder(tmp_path), FakeLocator()
        r.start_test(item())

        async def twice():
            for _ in range(2):
                await r.record(loc)
        asyncio.run(twice())
        assert len([c for c in loc.calls if "frameElement" not in c]) == 1

    def test_an_ambiguous_or_missing_element_is_not_recorded_and_never_raises(self, tmp_path):
        r = recorder(tmp_path)
        r.start_test(item())
        asyncio.run(r.record(FakeLocator({"items": [ITEM, ITEM], "page": {}})))
        asyncio.run(r.record(FakeLocator({"items": [], "page": {}})))

        class Boom:
            async def evaluate(self, *a, **k):
                raise RuntimeError("strict mode violation")
        asyncio.run(r.record(Boom()))
        assert [v for v in r.pending.values() if v] == []

    def test_the_probe_is_the_vendored_script_and_nothing_is_cached_from_a_service(self, tmp_path):
        from utils.heal_client import vendored_probe
        r = fp.Recorder(root=tmp_path, env={"HEAL_DIR": ".heal", "HEAL_SERVICE_URL": ""})
        assert r.probe_script() == vendored_probe()
        assert not (tmp_path / ".heal" / "probe.js").exists()

    def test_only_a_clean_green_test_writes(self, tmp_path):
        r = recorder(tmp_path)
        r.root = tmp_path
        passed = {"setup": "passed", "call": "passed", "teardown": "passed"}
        for label, it, outcomes, written in [
            ("clean", item(), passed, True),
            ("failed", item(), {**passed, "call": "failed"}, False),
            ("teardown error", item(), {**passed, "teardown": "failed"}, False),
            ("rerun", item(execution_count=2), passed, False),
            ("flaky marker", item(flaky=True), passed, False),
        ]:
            r.start_test(it)
            r.pending = {f"k-{label}": {"file": "pages/p.py", "text": "t", "page": "/p", "language": "en",
                                         "fingerprint": {"tag": "a"}}}
            r.outcomes = dict(outcomes)
            assert r.finish_test() is written, label
        assert list(fp.load_store(tmp_path / "fingerprints.json")["entries"]) == ["k-clean"]

    def test_unstable_tests_are_not_recorded(self, tmp_path, monkeypatch):
        import utils.stability_index as si
        monkeypatch.setattr(si, "get_stability", lambda nodeid: 0.2)
        r = recorder(tmp_path)
        r.start_test(item())
        r.outcomes = {"setup": "passed", "call": "passed", "teardown": "passed"}
        assert r.clean() is False


class TestSwitch:
    def test_off_by_default_and_never_during_a_heal(self):
        assert fp.enabled({}) is False
        assert fp.enabled({"HEAL_FINGERPRINTS": "off"}) is False
        assert fp.enabled({"HEAL_FINGERPRINTS": "on"}) is True
        assert fp.enabled({"HEAL_FINGERPRINTS": "ON", "HEAL_RUN": "1"}) is False

    def test_the_hooks_do_nothing_when_off(self, monkeypatch):
        monkeypatch.setattr(fp, "_RECORDER", None)
        fp.pytest_runtest_setup(item())
        fp.pytest_runtest_logreport(SimpleNamespace(when="teardown", outcome="passed"))

    def test_configure_leaves_playwright_untouched_when_off(self, monkeypatch):
        from playwright.async_api import Locator
        monkeypatch.delenv("HEAL_FINGERPRINTS", raising=False)
        before = Locator.click
        fp.pytest_configure(None)
        assert Locator.click is before and fp._RECORDER is None

    def test_install_wraps_acting_methods_once_and_records_before_acting(self, tmp_path, monkeypatch):
        from playwright.async_api import Locator
        saved = {n: getattr(Locator, n) for n in fp.ACTIONS if hasattr(Locator, n)}
        try:
            order, r = [], recorder(tmp_path)

            async def fake_record(loc):
                order.append("record")
            r.record = fake_record

            async def original(self, *a, **k):
                order.append("act")
                return "done"
            monkeypatch.setattr(Locator, "click", original)
            fp._install(r)
            fp._install(r)                                           # twice: still wrapped once
            assert asyncio.run(Locator.click(object())) == "done" and order == ["record", "act"]
        finally:
            for n, v in saved.items():
                setattr(Locator, n, v)


class TestServiceSchema:
    def test_what_is_recorded_is_accepted_by_the_real_service_schema(self):
        schemas = pytest.importorskip("heal_service.schemas", reason="heal-service is not installed")
        model = schemas.Fingerprint.model_validate(fp.item_to_fingerprint(ITEM, "f"))
        flat = model.flat()
        assert flat["id"] == "username" and flat["testid"] == "login-user" and flat["box"]["width"] == 280
        schemas.LastPass.model_validate(fp.last_pass_for(
            {"entries": {"k": {"page": "/p", "language": "en", "fingerprint": fp.item_to_fingerprint(ITEM)},
                         "n": {"page": "/p", "fingerprint": fp.item_to_fingerprint({**ITEM, "id": "pw"})}}}, "k"))
