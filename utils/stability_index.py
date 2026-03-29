"""Stability Index — track pass/fail per test, quarantine flaky tests."""
import json
import fcntl
from pathlib import Path
from datetime import datetime

HISTORY_FILE = Path(__file__).parent.parent / "data" / "stability_history.json"
DEFAULT_WINDOW = 10
DEFAULT_THRESHOLD = 0.7


def _load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            text = HISTORY_FILE.read_text()
            return json.loads(text) if text.strip() else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_history(data: dict) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(HISTORY_FILE)


def record_result(test_id: str, passed: bool, window: int = DEFAULT_WINDOW) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_file = HISTORY_FILE.with_suffix(".lock")
    with open(lock_file, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            history = _load_history()
            if test_id not in history:
                history[test_id] = {"results": [], "last_updated": ""}
            entry = history[test_id]
            entry["results"].append(1 if passed else 0)
            entry["results"] = entry["results"][-window:]  # keep last N
            entry["last_updated"] = datetime.now().isoformat()
            _save_history(history)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def get_stability(test_id: str) -> float:
    history = _load_history()
    entry = history.get(test_id)
    if not entry or not entry["results"]:
        return 1.0  # no history = assume stable
    return sum(entry["results"]) / len(entry["results"])


def get_unstable_tests(threshold: float = DEFAULT_THRESHOLD) -> list[str]:
    history = _load_history()
    unstable = []
    for test_id, entry in history.items():
        if entry["results"]:
            stability = sum(entry["results"]) / len(entry["results"])
            if stability < threshold:
                unstable.append(test_id)
    return unstable


def get_stability_report() -> dict:
    history = _load_history()
    report = {}
    for test_id, entry in history.items():
        results = entry["results"]
        if results:
            report[test_id] = {
                "stability": sum(results) / len(results),
                "runs": len(results),
                "last_updated": entry["last_updated"],
            }
    return report
