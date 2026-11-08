"""
===============================================================================
Unit Tests: utils/heal_followup.py and its use in scripts/heal.py (post-PR signals)
===============================================================================
`gh` and the heal service are fakes and the repository is a temp directory, so every outcome is tested without a network:
what is recorded when a PR is raised, what each PR state and file state becomes, that counts keep running when `gh` cannot
answer, that a failure again stays recorded, which entries finish, that a bad record file or address is never trusted, and that
a follow-up can never fail the run or edit a source file.

Author: PMAC
===============================================================================
"""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from utils import heal_followup as hf
from utils.heal_client import HealServiceError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import heal  # noqa: E402

DAY = 86400
NOW = 1_800_000_000.0
PR = "https://github.com/example-org/shop-e2e/pull/42"
FROM = "self.page.locator('#username')"
TO = 'self.page.get_by_test_id("login-user")'
HEALED = {"test": "test_login", "outcome": "healed", "heal_id": "h_abc123", "file": "pages/login_page.py", "from": FROM, "to": TO}


class Service:
    def __init__(self, error=None):
        self.error, self.sent = error, []

    def followup(self, heal_id, report):
        if self.error:
            raise self.error
        self.sent.append((heal_id, report))
        return {"heal_id": heal_id}


@pytest.fixture
def root(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "login_page.py").write_text(f"class P:\n    def go(self):\n        {TO}.fill('x')\n")
    return tmp_path


def recorded(root, **over):
    assert hf.record_heals(root, [{**HEALED, **over}], PR, now=NOW, env={}) == 1


def state(root, gh="merged", cases=(), now=NOW + 3 * DAY, service=None):
    service = service or Service()
    sent = hf.follow_up(root, service, list(cases), now=now, gh=lambda url: gh, env={})
    return sent, service


# ---- recording ---------------------------------------------------------------------------------------------------------
def test_a_raised_pr_records_each_healed_locator(root):
    recorded(root)
    data = json.loads((root / ".heal" / "heals.json").read_text())
    e = data["heals"][0]
    assert data["version"] == 1 and {k: e[k] for k in ("heal_id", "file", "from", "to", "test", "pr_url")} == {
        "heal_id": "h_abc123", "file": "pages/login_page.py", "from": FROM, "to": TO, "test": "test_login", "pr_url": PR}
    assert e["opened_at"] == NOW and e["runs"] == 0 and e["failed_again"] is False and e["done"] is False


def test_a_decision_without_a_heal_id_or_a_pr_without_a_url_is_not_recorded(root):
    shared = {**HEALED, "heal_id": None, "source": "same fix as another test"}
    assert hf.record_heals(root, [shared], PR, now=NOW, env={}) == 0
    assert hf.record_heals(root, [HEALED], "", now=NOW, env={}) == 0
    assert hf.record_heals(root, [HEALED], "not a url; rm -rf /", now=NOW, env={}) == 0
    assert hf.record_heals(root, [HEALED], "http://github.com/o/r/pull/1", now=NOW, env={}) == 0     # https only
    assert not (root / ".heal" / "heals.json").exists()


def test_recording_twice_does_not_duplicate_a_heal(root):
    recorded(root)
    assert hf.record_heals(root, [HEALED], PR, now=NOW + 5, env={}) == 0
    assert len(hf.load(root, {})) == 1


def test_the_pr_url_is_read_from_what_gh_printed():
    assert hf.pr_url_from(f"Creating pull request\n\n{PR}\n") == PR
    assert hf.pr_url_from("no url here") == "" and hf.pr_url_from("") == ""
    assert hf.pr_url_from("https://evil.example/x\n") == ""


# ---- what each PR and file state becomes ---------------------------------------------------------------------------------
def test_an_open_pr_is_reported_open_and_stays_tracked(root):
    recorded(root)
    sent, service = state(root, "open")
    assert service.sent == [("h_abc123", {"pr_state": "open", "failed_again": False, "runs_since": 0, "days_since": 3})]
    assert sent[0]["pr_state"] == "open" and hf.load(root, {})[0]["done"] is False


def test_a_pr_closed_without_merging_is_reported_and_finishes(root):
    recorded(root)
    _, service = state(root, "closed_unmerged")
    assert service.sent[0][1]["pr_state"] == "closed_unmerged" and hf.load(root, {})[0]["done"] is True
    sent, again = state(root, "closed_unmerged")
    assert sent == [] and again.sent == []                     # finished entries are not reported again


def test_a_merged_pr_whose_line_is_still_the_healed_one_is_merged_unchanged(root):
    recorded(root)
    assert state(root)[1].sent[0][1]["pr_state"] == "merged_unchanged"


def test_a_merged_pr_whose_line_a_person_changed_is_edited(root):
    recorded(root)
    (root / "pages" / "login_page.py").write_text("class P:\n    def go(self):\n        self.page.get_by_role('textbox').fill('x')\n")
    assert state(root)[1].sent[0][1]["pr_state"] == "edited"


def test_a_merged_pr_whose_line_is_back_to_the_old_one_is_reverted_and_finishes(root):
    recorded(root)
    (root / "pages" / "login_page.py").write_text(f"class P:\n    def go(self):\n        {FROM}.fill('x')\n")
    _, service = state(root)
    assert service.sent[0][1]["pr_state"] == "reverted" and hf.load(root, {})[0]["done"] is True


def test_the_file_is_never_edited_by_a_follow_up(root):
    recorded(root)
    before = (root / "pages" / "login_page.py").read_bytes()
    state(root)
    assert (root / "pages" / "login_page.py").read_bytes() == before


# ---- runs, failures, days -------------------------------------------------------------------------------------------------
def test_runs_and_days_since_count_and_a_failure_again_sticks(root):
    recorded(root)
    state(root, cases=[{"name": "test_login", "outcome": "passed"}], now=NOW + DAY)
    state(root, cases=[{"name": "test_login", "outcome": "failed"}], now=NOW + 2 * DAY)
    _, service = state(root, cases=[{"name": "test_login", "outcome": "passed"}, {"name": "other", "outcome": "failed"}],
                       now=NOW + 5 * DAY + 100)
    assert service.sent[0][1] == {"pr_state": "merged_unchanged", "failed_again": True, "runs_since": 3, "days_since": 5}


def test_a_skipped_or_missing_test_is_not_a_run(root):
    recorded(root)
    _, service = state(root, cases=[{"name": "test_login", "outcome": "skipped"}, {"name": "unrelated", "outcome": "passed"}])
    assert service.sent[0][1]["runs_since"] == 0


def test_counts_keep_running_while_gh_cannot_answer(root):
    recorded(root)
    sent, service = state(root, gh=None, cases=[{"name": "test_login", "outcome": "failed"}])
    assert sent == [] and service.sent == []                   # nothing to say yet
    _, service = state(root, cases=[{"name": "test_login", "outcome": "passed"}])
    assert service.sent[0][1]["runs_since"] == 2 and service.sent[0][1]["failed_again"] is True


def test_an_entry_finishes_after_ten_runs_and_thirty_days_with_an_answer_sent(root):
    recorded(root)
    for _ in range(9):
        state(root, cases=[{"name": "test_login", "outcome": "passed"}], now=NOW + 40 * DAY)
    assert hf.load(root, {})[0]["done"] is False               # ten runs, but not yet
    _, service = state(root, cases=[{"name": "test_login", "outcome": "passed"}], now=NOW + 40 * DAY)
    assert service.sent[0][1]["runs_since"] == 10 and service.sent[0][1]["days_since"] == 40 and hf.load(root, {})[0]["done"]


# ---- the service -------------------------------------------------------------------------------------------------------
def test_a_service_that_forgot_the_heal_finishes_the_entry(root):
    recorded(root)
    state(root, service=Service(HealServiceError("the heal service answered 404: no such heal")))
    assert hf.load(root, {})[0]["done"] is True


def test_a_service_that_is_down_keeps_the_entry_for_next_time(root):
    recorded(root)
    sent, _ = state(root, service=Service(HealServiceError("the heal service could not be reached (ConnectError)")))
    assert sent == [] and hf.load(root, {})[0]["done"] is False


# ---- the record file is untrusted ----------------------------------------------------------------------------------------
def test_malformed_entries_and_bad_addresses_are_dropped_not_trusted(root):
    good = {"heal_id": "h_ok", "file": "pages/login_page.py", "from": FROM, "to": TO, "test": "t", "pr_url": PR, "opened_at": NOW}
    bad = [{**good, "pr_url": "--web"}, {**good, "pr_url": "https://github.com/o/r/pull/1; rm -rf ~"}, {**good, "heal_id": "../x"},
           {**good, "opened_at": "yesterday"}, {**good, "from": ""}, {**good, "to": 5}, "string", None, {}]
    (root / ".heal").mkdir()
    (root / ".heal" / "heals.json").write_text(json.dumps({"version": 1, "heals": bad + [good]}))
    assert [e["heal_id"] for e in hf.load(root, {})] == ["h_ok"]
    (root / ".heal" / "heals.json").write_text("{not json")
    assert hf.load(root, {}) == []


def test_a_file_outside_the_source_roots_or_through_a_symlink_is_never_read(root, tmp_path):
    outside = tmp_path.parent / "outside_secret.py"
    outside.write_text(TO)
    (root / "pages" / "link.py").symlink_to(outside)
    for rel in ("../outside_secret.py", "pages/link.py", "/etc/hosts", "pages/missing.py", "conftest.py"):
        entry = {"heal_id": "h_x", "file": rel, "from": FROM, "to": TO, "test": "t", "pr_url": PR, "opened_at": NOW,
                 "runs": 0, "failed_again": False, "state": None, "done": False, "done_at": None}
        assert hf.line_state(root, entry, ("pages", "tests", "utils")) is None


def test_gh_is_run_with_an_argument_list_and_only_for_a_pull_request_url():
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"state": "MERGED"}))
    assert hf.gh_state(PR, run) == "merged" and calls == [["gh", "pr", "view", PR, "--json", "state"]]
    assert hf.gh_state("-h; echo hi", run) is None and len(calls) == 1
    for out, want in (("OPEN", "open"), ("CLOSED", "closed_unmerged"), ("DRAFT", None)):
        assert hf.gh_state(PR, lambda c, **k: SimpleNamespace(returncode=0, stdout=json.dumps({"state": out}))) == want


@pytest.mark.parametrize("boom", [FileNotFoundError("gh"), subprocess.TimeoutExpired("gh", 30), OSError("denied")])
def test_gh_missing_or_failing_means_unknown_not_an_error(boom):
    def run(cmd, **kw):
        raise boom
    assert hf.gh_state(PR, run) is None
    assert hf.gh_state(PR, lambda c, **k: SimpleNamespace(returncode=1, stdout="")) is None
    assert hf.gh_state(PR, lambda c, **k: SimpleNamespace(returncode=0, stdout="not json")) is None


def test_finished_entries_are_dropped_after_sixty_days(root):
    recorded(root)
    entries = hf.load(root, {})
    entries[0].update(done=True, done_at=NOW)
    hf.save(root, entries, {}, now=NOW + 59 * DAY)
    assert len(hf.load(root, {})) == 1
    hf.save(root, entries, {}, now=NOW + 61 * DAY)
    assert hf.load(root, {}) == []
    assert not list((root / ".heal").glob("*.tmp"))


# ---- scripts/heal.py ------------------------------------------------------------------------------------------------------
def test_a_follow_up_that_blows_up_never_fails_the_run(root, capsys):
    class Boom:
        def followup(self, *a):
            raise RuntimeError("down")
    recorded(root)
    assert heal.follow_up_heals(Boom(), [], root) == []        # gh is not signed in here: skipped, never raised
    out = heal.follow_up_heals(object(), [], root)
    assert out == []


def test_main_follows_up_before_it_decides_there_is_nothing_to_heal(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEAL_ARTIFACTS_DIR", str(tmp_path / "art"))
    monkeypatch.setenv("HEAL_SERVICE_URL", "http://localhost:8765")
    monkeypatch.setattr(sys, "argv", ["heal.py"])
    seen = {}

    def run_suite(kw=None):
        heal.LAST_CASES[:] = [{"name": "test_login", "outcome": "passed", "classname": "c", "error": ""}]
        return []
    monkeypatch.setattr(heal, "run_suite", run_suite)
    monkeypatch.setattr(heal, "follow_up_heals", lambda service, cases, root=None: seen.setdefault("cases", cases) and [])
    heal.main()
    assert seen["cases"][0]["name"] == "test_login" and "nothing to heal" in capsys.readouterr().out


def test_open_pr_returns_the_url_and_main_records_the_heals(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEAL_ARTIFACTS_DIR", str(tmp_path / "art"))
    monkeypatch.setenv("HEAL_SERVICE_URL", "http://localhost:8765")
    monkeypatch.setattr(sys, "argv", ["heal.py", "--open-pr"])
    monkeypatch.setattr(heal, "working_tree_dirty", lambda: False)
    monkeypatch.setattr(heal, "run_suite", lambda kw=None: [{"name": "test_login", "classname": "c", "error": ""}])
    monkeypatch.setattr(heal, "follow_up_heals", lambda *a, **k: [])
    fake = SimpleNamespace(heal=lambda f: dict(HEALED, outcome="healed", usage={}, files=["pages/login_page.py"]))
    monkeypatch.setattr(heal, "Healer", lambda *a, **k: fake)
    monkeypatch.setattr(heal, "open_pr", lambda healed, other: PR)
    heal.main()
    assert [e["heal_id"] for e in hf.load(tmp_path, {})] == ["h_abc123"] and hf.load(tmp_path, {})[0]["pr_url"] == PR


def test_open_pr_reads_the_url_gh_prints(monkeypatch):
    calls = []
    monkeypatch.setattr(heal.subprocess, "check_call", lambda cmd, **k: calls.append(cmd))
    monkeypatch.setattr(heal.subprocess, "check_output", lambda cmd, **k: f"https://github.com\n{PR}\n")
    assert heal.open_pr([HEALED], []) == PR
    assert any(c[:2] == ["git", "push"] for c in calls)


def test_recording_failure_after_the_pr_is_opened_does_not_fail_the_run(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEAL_ARTIFACTS_DIR", str(tmp_path / "art"))
    monkeypatch.setenv("HEAL_SERVICE_URL", "http://localhost:8765")
    monkeypatch.setattr(sys, "argv", ["heal.py", "--open-pr"])
    monkeypatch.setattr(heal, "working_tree_dirty", lambda: False)
    monkeypatch.setattr(heal, "run_suite", lambda kw=None: [{"name": "test_login", "classname": "c", "error": ""}])
    monkeypatch.setattr(heal, "follow_up_heals", lambda *a, **k: [])
    monkeypatch.setattr(heal, "Healer", lambda *a, **k: SimpleNamespace(heal=lambda f: dict(HEALED, usage={}, files=["x"])))
    monkeypatch.setattr(heal, "open_pr", lambda healed, other: PR)
    monkeypatch.setattr(heal, "record_heals", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    heal.main()
    assert "could not record the heals for follow-up" in capsys.readouterr().out
