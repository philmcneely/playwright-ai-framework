"""
Test Observability Collector for Playwright Test Framework

Records structured metrics per test execution: timing, status, retries,
heal events, error categories. Writes JSONL for analysis and generates
summary reports.

Conditionally enabled via OBSERVABILITY_ENABLED environment variable.

Environment Variables:
    OBSERVABILITY_ENABLED: Enable metric collection (true|false, default: false)
"""

import json
import os
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.artifact_paths import ARTIFACT_ROOT
from utils.debug import debug_print

OBSERVABILITY_DIR = ARTIFACT_ROOT / "observability"
METRICS_FILE = OBSERVABILITY_DIR / "metrics.jsonl"


@dataclass
class TestMetric:
    test_id: str
    test_name: str
    suite: str
    status: str
    duration_ms: int
    retry_count: int
    browser: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    commit_sha: Optional[str] = None
    branch: Optional[str] = None
    heal_event: bool = False
    heal_confidence: Optional[float] = None
    error_category: Optional[str] = None
    tags: Optional[list] = None


def _get_git_info():
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        return sha or None, branch or None
    except Exception:
        return None, None


def categorize_error(message: Optional[str]) -> Optional[str]:
    if not message:
        return None
    lower = message.lower()
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    if "locator" in lower or "selector" in lower or "not found" in lower:
        return "element-not-found"
    if "navigation" in lower or "net::" in lower:
        return "navigation"
    if "assert" in lower or "expect" in lower:
        return "assertion"
    if "crash" in lower or "target closed" in lower:
        return "browser-crash"
    return "other"


class TestObservabilityCollector:
    def __init__(self):
        self.enabled = os.getenv("OBSERVABILITY_ENABLED", "false").lower() == "true"
        self.metrics: list[TestMetric] = []
        self.retry_tracker: dict[str, int] = {}
        self._commit_sha, self._branch = _get_git_info()

    def track_retry(self, test_id: str):
        self.retry_tracker[test_id] = self.retry_tracker.get(test_id, 0) + 1

    def get_retry_count(self, test_id: str) -> int:
        return self.retry_tracker.get(test_id, 0)

    def record(self, metric: TestMetric):
        if not self.enabled:
            return
        if metric.commit_sha is None:
            metric.commit_sha = self._commit_sha
        if metric.branch is None:
            metric.branch = self._branch
        self.metrics.append(metric)
        self._append_to_file(metric)

    def _append_to_file(self, metric: TestMetric):
        try:
            OBSERVABILITY_DIR.mkdir(parents=True, exist_ok=True)
            with open(METRICS_FILE, "a") as f:
                f.write(json.dumps(asdict(metric)) + "\n")
        except Exception as e:
            debug_print(f"[Observability] Failed to write metric: {e}")

    def summarize(self) -> dict:
        total = len(self.metrics)
        passed = sum(1 for m in self.metrics if m.status == "passed")
        failed = sum(1 for m in self.metrics if m.status == "failed")
        skipped = sum(1 for m in self.metrics if m.status == "skipped")
        flake_count = sum(
            1 for m in self.metrics if m.retry_count > 0 and m.status == "passed"
        )
        total_duration = sum(m.duration_ms for m in self.metrics)
        heal_events = sum(1 for m in self.metrics if m.heal_event)

        failures_by_category: dict[str, int] = {}
        for m in self.metrics:
            if m.status == "failed" and m.error_category:
                failures_by_category[m.error_category] = (
                    failures_by_category.get(m.error_category, 0) + 1
                )

        slowest = sorted(self.metrics, key=lambda m: m.duration_ms, reverse=True)[:10]

        return {
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "flake_count": flake_count,
            "total_duration_ms": total_duration,
            "avg_duration_ms": round(total_duration / total) if total else 0,
            "heal_events": heal_events,
            "pass_rate": round(passed / total * 100, 2) if total else 0,
            "flake_rate": round(flake_count / total * 100, 2) if total else 0,
            "slowest_tests": [
                {"name": m.test_name, "duration_ms": m.duration_ms} for m in slowest
            ],
            "failures_by_category": failures_by_category,
        }

    def write_report(self):
        if not self.enabled or not self.metrics:
            return

        summary = self.summarize()
        OBSERVABILITY_DIR.mkdir(parents=True, exist_ok=True)

        with open(OBSERVABILITY_DIR / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        s = summary
        md = f"""# Test Observability Report

**Generated:** {datetime.now(timezone.utc).isoformat()}

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | {s["total_tests"]} |
| Passed | {s["passed"]} |
| Failed | {s["failed"]} |
| Skipped | {s["skipped"]} |
| Pass Rate | {s["pass_rate"]}% |
| Flake Count | {s["flake_count"]} |
| Flake Rate | {s["flake_rate"]}% |
| Heal Events | {s["heal_events"]} |
| Total Duration | {s["total_duration_ms"] / 1000:.1f}s |
| Avg Duration | {s["avg_duration_ms"] / 1000:.1f}s |

## Slowest Tests

"""
        for i, t in enumerate(s["slowest_tests"], 1):
            md += f"{i}. **{t['name']}** — {t['duration_ms'] / 1000:.1f}s\n"

        md += "\n## Failures by Category\n\n"
        if s["failures_by_category"]:
            for cat, count in s["failures_by_category"].items():
                md += f"- **{cat}:** {count}\n"
        else:
            md += "_No categorized failures_\n"

        md += "\n---\n_Generated by playwright-ai-framework observability_\n"

        with open(OBSERVABILITY_DIR / "report.md", "w") as f:
            f.write(md)

        print(f"[Observability] Report written to {OBSERVABILITY_DIR / 'report.md'}")

    def print_summary(self):
        if not self.enabled or not self.metrics:
            return

        s = self.summarize()
        sep = "=" * 60
        print(f"\n{sep}")
        print("TEST OBSERVABILITY SUMMARY")
        print(sep)
        print(
            f"  Total: {s['total_tests']} | Pass: {s['passed']} | Fail: {s['failed']} | Skip: {s['skipped']}"
        )
        print(f"  Pass Rate: {s['pass_rate']}% | Flake Rate: {s['flake_rate']}%")
        print(f"  Heal Events: {s['heal_events']}")
        print(
            f"  Duration: {s['total_duration_ms'] / 1000:.1f}s (avg {s['avg_duration_ms'] / 1000:.1f}s)"
        )
        if s["slowest_tests"]:
            print(
                f"  Slowest: {s['slowest_tests'][0]['name']} ({s['slowest_tests'][0]['duration_ms'] / 1000:.1f}s)"
            )
        print(f"{sep}\n")


_collector: Optional[TestObservabilityCollector] = None


def get_observability_collector() -> TestObservabilityCollector:
    global _collector
    if _collector is None:
        _collector = TestObservabilityCollector()
    return _collector
