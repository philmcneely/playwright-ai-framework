"""Tests for stability index tracking."""
import json
import pytest
from pathlib import Path
from utils.stability_index import (
    record_result, get_stability, get_unstable_tests,
    get_stability_report, HISTORY_FILE, _save_history
)


@pytest.fixture(autouse=True)
def clean_history(tmp_path, monkeypatch):
    """Use temp file for tests."""
    test_file = tmp_path / "stability_history.json"
    monkeypatch.setattr("utils.stability_index.HISTORY_FILE", test_file)
    yield
    if test_file.exists():
        test_file.unlink()


def test_record_and_get_stability():
    for _ in range(7):
        record_result("test_login", True)
    for _ in range(3):
        record_result("test_login", False)
    stability = get_stability("test_login")
    assert stability == 0.7


def test_unknown_test_returns_stable():
    assert get_stability("nonexistent") == 1.0


def test_window_limit():
    for _ in range(15):
        record_result("test_window", True)
    report = get_stability_report()
    assert report["test_window"]["runs"] == 10  # default window


def test_unstable_detection():
    for _ in range(10):
        record_result("test_flaky", False)
    for _ in range(10):
        record_result("test_solid", True)
    unstable = get_unstable_tests(0.7)
    assert "test_flaky" in unstable
    assert "test_solid" not in unstable


def test_stability_report():
    record_result("test_a", True)
    record_result("test_a", False)
    report = get_stability_report()
    assert "test_a" in report
    assert report["test_a"]["stability"] == 0.5
    assert report["test_a"]["runs"] == 2
