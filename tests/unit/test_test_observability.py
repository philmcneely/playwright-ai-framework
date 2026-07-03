"""
===============================================================================
Unit Tests: utils/test_observability.py
===============================================================================
Tests the pure logic of the observability collector — error categorization,
metric recording, and summary aggregation — without any browser dependency.

Author: PMAC
===============================================================================
"""

import json

import pytest

from utils import test_observability as obs
from utils.test_observability import (
    TestMetric,
    TestObservabilityCollector,
    categorize_error,
)


def make_metric(**overrides):
    """Build a TestMetric with sensible defaults for unit testing."""
    defaults = {
        "test_id": "tests/unit/test_x.py::test_x",
        "test_name": "test_x",
        "suite": "tests/unit/test_x.py",
        "status": "passed",
        "duration_ms": 100,
        "retry_count": 0,
        "browser": "chromium",
    }
    defaults.update(overrides)
    return TestMetric(**defaults)


# ------------------------------------------------------------------------------
# categorize_error
# ------------------------------------------------------------------------------


class TestCategorizeError:
    def test_none_message_returns_none(self):
        assert categorize_error(None) is None

    def test_empty_message_returns_none(self):
        assert categorize_error("") is None

    @pytest.mark.parametrize(
        "message,expected",
        [
            ("Timeout 30000ms exceeded", "timeout"),
            ("The request timed out", "timeout"),
            ("waiting for locator('#username')", "element-not-found"),
            ("selector resolved to hidden element", "element-not-found"),
            ("element not found on page", "element-not-found"),
            ("net::ERR_CONNECTION_REFUSED", "navigation"),
            ("Navigation to page failed", "navigation"),
            ("AssertionError: values differ", "assertion"),
            ("expect(received).toBe(expected)", "assertion"),
            ("Target closed", "browser-crash"),
            ("browser crash detected", "browser-crash"),
            ("something completely different", "other"),
        ],
    )
    def test_categories(self, message, expected):
        assert categorize_error(message) == expected

    def test_case_insensitive(self):
        assert categorize_error("TIMEOUT WAITING") == "timeout"

    def test_timeout_takes_precedence_over_locator(self):
        # Categories are checked in order; timeout wins over element-not-found.
        assert categorize_error("Timeout waiting for locator('#x')") == "timeout"


# ------------------------------------------------------------------------------
# TestObservabilityCollector.summarize
# ------------------------------------------------------------------------------


class TestSummarize:
    def _collector(self):
        collector = TestObservabilityCollector()
        collector.enabled = True
        return collector

    def test_empty_summary_has_zero_totals(self):
        summary = self._collector().summarize()
        assert summary["total_tests"] == 0
        assert summary["passed"] == 0
        assert summary["failed"] == 0
        assert summary["skipped"] == 0
        assert summary["pass_rate"] == 0
        assert summary["flake_rate"] == 0
        assert summary["avg_duration_ms"] == 0
        assert summary["slowest_tests"] == []
        assert summary["failures_by_category"] == {}

    def test_status_counts_and_pass_rate(self):
        collector = self._collector()
        collector.metrics = [
            make_metric(status="passed"),
            make_metric(status="passed"),
            make_metric(status="failed", error_category="timeout"),
            make_metric(status="skipped"),
        ]
        summary = collector.summarize()
        assert summary["total_tests"] == 4
        assert summary["passed"] == 2
        assert summary["failed"] == 1
        assert summary["skipped"] == 1
        assert summary["pass_rate"] == 50.0

    def test_flake_is_passed_after_retry(self):
        collector = self._collector()
        collector.metrics = [
            make_metric(status="passed", retry_count=1),
            make_metric(status="passed", retry_count=0),
            make_metric(status="failed", retry_count=3),
            make_metric(status="passed"),
        ]
        summary = collector.summarize()
        assert summary["flake_count"] == 1
        assert summary["flake_rate"] == 25.0

    def test_failures_grouped_by_category(self):
        collector = self._collector()
        collector.metrics = [
            make_metric(status="failed", error_category="timeout"),
            make_metric(status="failed", error_category="timeout"),
            make_metric(status="failed", error_category="assertion"),
            make_metric(status="failed", error_category=None),
            make_metric(status="passed", error_category="timeout"),
        ]
        summary = collector.summarize()
        assert summary["failures_by_category"] == {"timeout": 2, "assertion": 1}

    def test_duration_totals_and_slowest_order(self):
        collector = self._collector()
        collector.metrics = [
            make_metric(test_name="fast", duration_ms=100),
            make_metric(test_name="slow", duration_ms=900),
            make_metric(test_name="medium", duration_ms=500),
        ]
        summary = collector.summarize()
        assert summary["total_duration_ms"] == 1500
        assert summary["avg_duration_ms"] == 500
        names = [t["name"] for t in summary["slowest_tests"]]
        assert names == ["slow", "medium", "fast"]

    def test_slowest_tests_capped_at_ten(self):
        collector = self._collector()
        collector.metrics = [
            make_metric(test_name=f"t{i}", duration_ms=i) for i in range(15)
        ]
        assert len(collector.summarize()["slowest_tests"]) == 10

    def test_heal_events_counted(self):
        collector = self._collector()
        collector.metrics = [
            make_metric(heal_event=True),
            make_metric(heal_event=False),
        ]
        assert collector.summarize()["heal_events"] == 1


# ------------------------------------------------------------------------------
# TestObservabilityCollector.record
# ------------------------------------------------------------------------------


class TestRecord:
    def test_record_skipped_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(obs, "OBSERVABILITY_DIR", tmp_path)
        monkeypatch.setattr(obs, "METRICS_FILE", tmp_path / "metrics.jsonl")
        collector = TestObservabilityCollector()
        collector.enabled = False

        collector.record(make_metric())

        assert collector.metrics == []
        assert not (tmp_path / "metrics.jsonl").exists()

    def test_record_appends_metric_and_writes_jsonl(self, tmp_path, monkeypatch):
        monkeypatch.setattr(obs, "OBSERVABILITY_DIR", tmp_path)
        monkeypatch.setattr(obs, "METRICS_FILE", tmp_path / "metrics.jsonl")
        collector = TestObservabilityCollector()
        collector.enabled = True

        collector.record(make_metric(test_name="recorded"))
        collector.record(make_metric(test_name="recorded_2"))

        assert len(collector.metrics) == 2
        lines = (tmp_path / "metrics.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["test_name"] == "recorded"
        assert first["status"] == "passed"

    def test_record_backfills_git_info(self, tmp_path, monkeypatch):
        monkeypatch.setattr(obs, "OBSERVABILITY_DIR", tmp_path)
        monkeypatch.setattr(obs, "METRICS_FILE", tmp_path / "metrics.jsonl")
        collector = TestObservabilityCollector()
        collector.enabled = True
        collector._commit_sha = "abc1234"
        collector._branch = "unit-test-branch"

        metric = make_metric()
        collector.record(metric)

        assert metric.commit_sha == "abc1234"
        assert metric.branch == "unit-test-branch"

    def test_record_preserves_explicit_git_info(self, tmp_path, monkeypatch):
        monkeypatch.setattr(obs, "OBSERVABILITY_DIR", tmp_path)
        monkeypatch.setattr(obs, "METRICS_FILE", tmp_path / "metrics.jsonl")
        collector = TestObservabilityCollector()
        collector.enabled = True
        collector._commit_sha = "abc1234"

        metric = make_metric(commit_sha="explicit", branch="explicit-branch")
        collector.record(metric)

        assert metric.commit_sha == "explicit"
        assert metric.branch == "explicit-branch"
