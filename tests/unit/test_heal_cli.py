"""
===============================================================================
Unit Tests: scripts/heal.py — selector extraction, source location, model-output
validation, verification and revert-on-failure
===============================================================================
No browser, model endpoint or real pytest subprocess is used; those seams are
monkeypatched so the parsing and mutation decisions are tested in isolation.

Author: PMAC
===============================================================================
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "heal_cli", Path(__file__).resolve().parents[2] / "scripts" / "heal.py"
)
heal = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(heal)

ORIGINAL = "self.page.locator('#old')"


class TestBrokenSelector:
    def test_locator_literal(self):
        assert heal.broken_selector_from("waiting for locator('#old')") == "#old"

    def test_none_when_absent(self):
        assert heal.broken_selector_from("AssertionError: x == y") is None


class TestLocateInSource:
    def _tree(self, tmp_path, files):
        for rel, text in files.items():
            f = tmp_path / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
        return tmp_path

    def test_finds_css_selector_with_regex_metacharacters(self, tmp_path):
        sel = "button[type='submit']"
        root = self._tree(tmp_path, {"pages/p.py": 'x = self.page.locator("button[type=\'submit\']")\n'})
        loc = heal.locate_in_source(sel, root=root)
        assert loc["call"] == 'self.page.locator("button[type=\'submit\']")'
        assert loc["file"].replace("\\", "/") == "pages/p.py"

    def test_not_found(self, tmp_path):
        root = self._tree(tmp_path, {"pages/p.py": "x = 1\n"})
        assert heal.locate_in_source("#nope", root=root) is None

    def test_duplicate_locator_is_ambiguous(self, tmp_path):
        root = self._tree(tmp_path, {
            "pages/a.py": "self.page.locator('#old')\nself.page.locator('#old')\n",
            "pages/b.py": "self.page.locator('#old')\n",
        })
        assert heal.locate_in_source("#old", root=root) == {"ambiguous": 3}


class TestValidateReplacement:
    @pytest.mark.parametrize("good", [
        "self.page.get_by_label('Username')",
        "self.page.get_by_role('button', name='Login')",
        "self.page.locator('#a').first",
    ])
    def test_accepts_semantic_locators(self, good):
        assert heal.validate_replacement(good, ORIGINAL) == good

    @pytest.mark.parametrize("bad", [
        "",
        "; __import__('os').system('x')",
        "self.page.locator('#a'); import os",
        "self.page.get_by_label('a')\nimport os",
        "__import__('os').system('id')",
        "self.page.evaluate('1')",
        "self.page.get_by_label(open('/etc/passwd').read())",
        "other.get_by_label('a')",
        "self.page.get_by_label(",
    ])
    def test_rejects_unsafe_or_malformed(self, bad):
        assert heal.validate_replacement(bad, ORIGINAL) is None

    def test_receiver_must_match_original(self):
        assert heal.validate_replacement("page.get_by_label('a')", ORIGINAL) is None


def test_apply_replacement_touches_only_located_occurrence(tmp_path):
    src = "a = self.page.locator('#old')\n# unrelated '#old' text\nb = other\n"
    m = src.index("self.page.locator('#old')")
    loc = {"src": src, "start": m, "end": m + len(ORIGINAL) + 0}
    out = heal.apply_replacement(loc, "self.page.get_by_label('X')")
    assert out.count("get_by_label") == 1 and "# unrelated '#old' text" in out


class TestVerifyPassed:
    T = {"name": "test_a", "classname": "tests.t"}

    def _runner(self, rc, cases):
        return lambda keyword: (rc, cases)

    def test_pass(self):
        r = self._runner(0, [{"name": "test_a", "classname": "tests.t", "outcome": "passed"}])
        assert heal.verify_passed(self.T, r)

    def test_empty_selection_is_not_a_pass(self):
        assert not heal.verify_passed(self.T, self._runner(5, []))
        assert not heal.verify_passed(self.T, self._runner(0, []))

    def test_target_did_not_run(self):
        r = self._runner(0, [{"name": "test_other", "classname": "tests.t", "outcome": "passed"}])
        assert not heal.verify_passed(self.T, r)

    def test_nonzero_exit_or_failure_is_not_a_pass(self):
        ok = {"name": "test_a", "classname": "tests.t", "outcome": "passed"}
        assert not heal.verify_passed(self.T, self._runner(1, [ok]))
        bad = dict(ok, outcome="failed")
        assert not heal.verify_passed(self.T, self._runner(0, [bad]))


class TestMainFlow:
    def _setup(self, tmp_path, monkeypatch, proposal, passes):
        page = tmp_path / "pages" / "p.py"
        page.parent.mkdir(parents=True)
        page.write_text("class P:\n    def go(self):\n        self.page.locator('#old').click()\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(heal, "HEAL_BASE_URL", "http://x")
        monkeypatch.setattr(heal, "HEAL_MODEL", "m")
        monkeypatch.setattr(sys, "argv", ["heal.py"])
        monkeypatch.setattr(heal, "run_suite", lambda kw=None: [
            {"name": "test_a", "classname": "tests.t", "error": "waiting for locator('#old')"}])
        monkeypatch.setattr(heal, "aria_snapshot", lambda route: "- button")
        monkeypatch.setattr(heal, "propose_replacement", lambda call, snap: proposal)
        monkeypatch.setattr(heal, "verify_passed", lambda test: passes)
        return page

    def test_heals_when_verified(self, tmp_path, monkeypatch, capsys):
        page = self._setup(tmp_path, monkeypatch, "self.page.get_by_role('button')", True)
        heal.main()
        assert "get_by_role('button')" in page.read_text()
        assert "'healed'" in capsys.readouterr().out

    def test_reverts_when_not_verified(self, tmp_path, monkeypatch, capsys):
        page = self._setup(tmp_path, monkeypatch, "self.page.get_by_role('button')", False)
        before = page.read_text()
        heal.main()
        assert page.read_text() == before
        assert "reverted" in capsys.readouterr().out

    def test_malicious_model_output_never_written(self, tmp_path, monkeypatch, capsys):
        page = self._setup(tmp_path, monkeypatch, "__import__('os').system('id')", True)
        before = page.read_text()
        heal.main()
        assert page.read_text() == before
        assert "no usable" in capsys.readouterr().out

    def test_failures_beyond_max_are_reported(self, tmp_path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch, "self.page.get_by_role('button')", True)
        monkeypatch.setattr(sys, "argv", ["heal.py", "--max", "0"])
        heal.main()
        assert "beyond --max" in capsys.readouterr().out
