"""
===============================================================================
Unit Tests: scripts/heal.py — the CLI around the heal-service client: replacement
validation, verification, decisions beyond --max, shared-fix confirmation, the
summary file, the printed usage and the exit when no service is configured
===============================================================================
No browser, heal service or real pytest subprocess is used; those seams are
replaced so the CLI's own decisions are tested in isolation. The client's
request building, patch safety and try->result loop are in test_heal_client.py.

Author: PMAC
===============================================================================
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "heal_cli", Path(__file__).resolve().parents[2] / "scripts" / "heal.py"
)
heal = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(heal)

ORIGINAL = "self.page.locator('#old')"


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


class FakeHealer:
    """Stands in for utils.heal_client.Healer: one scripted decision per failure."""

    def __init__(self, decisions):
        self.decisions, self.seen = list(decisions), []

    def heal(self, failure):
        self.seen.append(failure["name"])
        return {"test": failure["name"], **self.decisions.pop(0)}


HEALED = {"outcome": "healed", "file": "pages/p.py", "from": "a", "to": "b", "files": ["pages/p.py"],
          "usage": {"calls": 1, "input_tokens": 120, "output_tokens": 8, "images": 0}}
HUMAN = {"outcome": "needs_human", "reason": "target_missing", "why": "no element could be the one",
         "usage": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "images": 0}}
FAILS = [{"name": f"test_{i}", "classname": "tests.t", "error": "e"} for i in range(3)]


class TestHealFailures:
    def test_failures_beyond_max_are_recorded_not_dropped(self):
        healer = FakeHealer([HUMAN])
        out = heal.heal_failures(FAILS, healer, 1)
        assert healer.seen == ["test_0"]
        beyond = [d for d in out if d.get("reason") == "beyond_max"]
        assert [d["test"] for d in beyond] == ["test_1", "test_2"] and "beyond --max 1" in beyond[0]["why"]
        assert all(d["outcome"] == "needs_human" for d in beyond)

    def test_a_test_a_previous_heal_already_fixed_is_confirmed_by_a_rerun_not_healed_again(self):
        healer = FakeHealer([HEALED, HUMAN])
        reruns = []
        out = heal.heal_failures(FAILS, healer, 10, verify=lambda f: reruns.append(f["name"]) or f["name"] == "test_1")
        assert reruns == ["test_1", "test_2"] and healer.seen == ["test_0", "test_2"]
        assert out[1]["outcome"] == "healed" and "same fix as test_0" in out[1]["source"]
        assert out[2]["outcome"] == "needs_human"


class TestSummaryAndOutput:
    def test_summary_file_has_counts_usage_and_every_decision(self, tmp_path):
        ds = [{"test": "a", **HEALED}, {"test": "b", **HUMAN}, {"test": "c", "outcome": "not_drift", "why": "assertion"}]
        path = heal.write_summary(ds, "t0", "run1", tmp_path / "art")
        data = json.loads(path.read_text())
        assert path.name == "heal-summary.json" and data["run_id"] == "run1"
        assert data["counts"] == {"healed": 1, "needs_human": 1, "not_drift": 1}
        assert data["usage"] == {"calls": 1, "input_tokens": 120, "output_tokens": 8, "images": 0}
        assert [d["test"] for d in data["decisions"]] == ["a", "b", "c"] and data["failures"] == 3

    def test_decisions_are_printed_with_tokens_and_a_run_total(self, capsys):
        heal.print_decisions([{"test": "a", **HEALED}, {"test": "b", **HUMAN}])
        out = capsys.readouterr().out
        assert "[healed] a: pages/p.py: a -> b  (tokens 120 in / 8 out, 1 call(s))" in out
        assert "[needs_human] [target_missing] b: no element could be the one" in out
        assert "run total: 1 model call(s), 120 input / 8 output tokens, 0 image(s)" in out


class TestMain:
    def _env(self, monkeypatch, tmp_path, url="http://localhost:8765"):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HEAL_ARTIFACTS_DIR", str(tmp_path / "art"))
        monkeypatch.delenv("HEAL_VISION", raising=False)
        (monkeypatch.setenv("HEAL_SERVICE_URL", url) if url else monkeypatch.delenv("HEAL_SERVICE_URL", raising=False))
        monkeypatch.setattr(sys, "argv", ["heal.py"])

    def test_no_service_url_exits_2_with_a_message(self, tmp_path, monkeypatch, capsys):
        self._env(monkeypatch, tmp_path, url=None)
        with pytest.raises(SystemExit) as e:
            heal.main()
        assert e.value.code == 2 and "HEAL_SERVICE_URL" in capsys.readouterr().out

    def test_no_failures_means_nothing_to_heal(self, tmp_path, monkeypatch, capsys):
        self._env(monkeypatch, tmp_path)
        monkeypatch.setattr(heal, "run_suite", lambda kw=None: [])
        heal.main()
        assert "nothing to heal" in capsys.readouterr().out

    def test_full_run_prints_decisions_writes_the_summary_and_never_opens_a_pr_unasked(self, tmp_path, monkeypatch, capsys):
        self._env(monkeypatch, tmp_path)
        monkeypatch.setattr(heal, "run_suite", lambda kw=None: FAILS[:2])
        fake = FakeHealer([HEALED, HUMAN])
        monkeypatch.setattr(heal, "Healer", lambda *a, **k: fake)
        monkeypatch.setattr(heal, "open_pr", lambda *a: pytest.fail("no --open-pr was given"))
        heal.main()
        out = capsys.readouterr().out
        assert "1 healed, 1 for human review" in out and "run total" in out
        assert json.loads((tmp_path / "art" / "heal-summary.json").read_text())["counts"]["healed"] == 1

    def test_vision_auto_says_a_masked_screenshot_is_sent_and_an_unknown_value_runs_with_vision_off(self, tmp_path, monkeypatch, capsys):
        self._env(monkeypatch, tmp_path)
        monkeypatch.setattr(heal, "run_suite", lambda kw=None: [])
        monkeypatch.setenv("HEAL_VISION", "auto")
        heal.main()
        assert "one masked viewport screenshot is sent per failure" in capsys.readouterr().out
        monkeypatch.setenv("HEAL_VISION", "full")
        heal.main()
        out = capsys.readouterr().out
        assert "running with vision off, no screenshot is taken" in out and "masked viewport" not in out

    def test_pytest_children_run_with_heal_run_set_so_fingerprints_are_not_recorded(self, monkeypatch):
        seen = {}

        def fake_run(cmd, env, capture_output):
            seen.update(env)
            raise FileNotFoundError

        monkeypatch.setattr(heal.subprocess, "run", fake_run)
        with pytest.raises(FileNotFoundError):
            heal.run_pytest("x")
        assert seen["HEAL_RUN"] == "1"

    def test_no_model_settings_remain_in_the_script_or_client(self):
        root = Path(__file__).resolve().parents[2]
        text = " ".join((root / p).read_text() for p in ("scripts/heal.py", "utils/heal_client.py",
                                                          "utils/heal_fingerprints.py", "utils/heal_locale.py"))
        for banned in ("HEAL_BASE_URL", "HEAL_MODEL", "HEAL_API_KEY", "chat/completions", "propose_replacement",
                       "max_tokens", "temperature"):
            assert banned not in text, banned
