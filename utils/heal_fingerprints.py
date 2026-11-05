"""
===============================================================================
Heal Fingerprints (pytest plugin: what each locator hit on the last green run)
===============================================================================
The heal service can settle many heals with no model call when it knows which element a locator hit the last time its test
passed: it looks for that same element on the drifted page (same test id, id, name, role, position). This plugin records
that knowledge. For every locator a clean green test ACTS ON (click, fill, check, ...), it saves what the page-probe sees of
the element, its box, its frame, the page path and language, into `.heal/fingerprints.json`, keyed by the source line that
acted on it. At heal time `scripts/heal.py` looks the failing line up and sends the result as `last_pass`, together with the
other elements recorded on the same page (`neighbours`), so the service can tell a renamed element from a different one.

It holds attributes, copy and boxes only. Never input values (the probe does not read them), screenshots or HTML.

Off unless HEAL_FINGERPRINTS=on, and then it costs one small in-page call per distinct locator line per test. With it off,
the hooks below return at once and no Playwright class is touched.

A fingerprint is written only from a clean green test: the test passed, ran once (no rerun), is not marked flaky and has not
a low stability index, and it is not running inside a heal (HEAL_RUN is set by scripts/heal.py). Anything else is dropped.

Features:
    ✓ Key = (source file, normalized text of the acting line): the same key at record time and at heal time
    ✓ Facts come from the service's own probe (GET /v1/probe.js, run on the one element), so Python and TypeScript clients
      record the same data; the script is cached in `.heal/probe.js` so a later offline run still works
    ✓ `.heal/fingerprints.json` is written atomically (temp file + rename) under a file lock, merged with what other
      workers wrote, and only rewritten when something changed
    ✓ `.heal/.gitignore` containing `*` is written automatically, so the cache is never committed by accident; set
      HEAL_FINGERPRINTS_COMMIT=on to opt in to committing the file (the ignore file is then not created)
    ✓ Never raises into a test: a recording failure only means no fingerprint for that locator

Environment Variables:
    HEAL_FINGERPRINTS: "on" to record (default off)
    HEAL_FINGERPRINTS_COMMIT: "on" to allow committing .heal/ (default off: .heal/.gitignore with `*` is written)
    HEAL_DIR: where the cache lives (default .heal)
    HEAL_SOURCE_ROOTS: comma separated source roots whose lines are recorded (default pages,tests,utils)
    HEAL_SERVICE_URL, HEAL_SERVICE_TOKEN: where the probe script is fetched from
    HEAL_RUN: set by scripts/heal.py while it runs the suite; nothing is recorded then

Author: PMAC
===============================================================================
"""
import json
import linecache
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

try:                                     # POSIX file locking; without it the merge is simply unlocked
    import fcntl
except ImportError:                      # pragma: no cover
    fcntl = None

VERSION = 1
DEFAULT_ROOTS = ("pages", "tests", "utils")
ACTIONS = ("click", "dblclick", "fill", "check", "uncheck", "set_checked", "select_option", "press", "type", "hover",
           "wait_for")
MAX_NEIGHBOURS = 100                     # the service accepts at most this many
_TEXT_KEYS = ("tag", "type", "role", "name", "label", "placeholder", "text", "row")
_ATTR_NAMES = {"testid": "data-testid", "id": "id", "name_attr": "name", "aria_label": "aria-label", "title": "title",
               "alt": "alt", "class": "class"}
_FIELD_MAX = 400


# ---- settings --------------------------------------------------------------------------------------------------------
def source_roots(env: Optional[Dict[str, str]] = None) -> Tuple[str, ...]:
    """The source roots (HEAL_SOURCE_ROOTS, comma separated, relative), default pages, tests, utils."""
    raw = (env if env is not None else os.environ).get("HEAL_SOURCE_ROOTS", "")
    roots = tuple(r.strip().strip("/") for r in raw.split(",") if r.strip().strip("/") and ".." not in r)
    return roots or DEFAULT_ROOTS


def heal_dir(root: Path, env: Optional[Dict[str, str]] = None) -> Path:
    return root / (env if env is not None else os.environ).get("HEAL_DIR", ".heal")


def enabled(env: Optional[Dict[str, str]] = None) -> bool:
    """True when fingerprints should be recorded: HEAL_FINGERPRINTS=on and not inside a heal run."""
    env = env if env is not None else os.environ
    return env.get("HEAL_FINGERPRINTS", "").lower() == "on" and not env.get("HEAL_RUN")


# ---- keys ------------------------------------------------------------------------------------------------------------
def normalize_line(text: str) -> str:
    """A source line without its indentation, comments' spacing, or quote style: the stable text of what acted."""
    return re.sub(r"\s+", " ", (text or "").strip()).replace('"', "'")


def call_key(file: str, text: str) -> str:
    return f"{file}::{normalize_line(text)}"


def line_of(root: Path, file: str, line: int) -> str:
    """The normalized text of line `line` of `file` as it is on disk now ('' when it cannot be read)."""
    try:
        lines = (root / file).read_text(encoding="utf-8").splitlines()
        return normalize_line(lines[line - 1]) if 1 <= line <= len(lines) else ""
    except (OSError, UnicodeDecodeError):
        return ""


def relative_under(path: str, root: Path, roots: Tuple[str, ...]) -> Optional[str]:
    """`path` as a posix path relative to `root` when it sits under one of `roots`, else None."""
    try:
        rel = Path(path).resolve().relative_to(root.resolve()) if Path(path).is_absolute() else Path(path)
    except (ValueError, OSError):
        return None
    posix = rel.as_posix()
    if posix.startswith("../") or posix.startswith("/") or ".." in rel.parts:
        return None
    return posix if any(posix.startswith(r + "/") for r in roots) else None


def call_site(root: Path, roots: Tuple[str, ...], depth: int = 1) -> Optional[Tuple[str, int, str]]:
    """(file, line, text) of the innermost caller under the source roots, skipping the heal helpers themselves."""
    frame = sys._getframe(depth)
    while frame is not None:
        rel = relative_under(frame.f_code.co_filename, root, roots)
        if rel and not rel.startswith("utils/heal_"):
            return rel, frame.f_lineno, linecache.getline(frame.f_code.co_filename, frame.f_lineno)
        frame = frame.f_back
    return None


# ---- the facts -------------------------------------------------------------------------------------------------------
def item_to_fingerprint(item: Dict[str, Any], frame: str = "") -> Dict[str, Any]:
    """A probe item as the service's fingerprint shape: copy and role facts, an attrs bag, a w/h box, never a value."""
    fp: Dict[str, Any] = {k: str(item[k])[:_FIELD_MAX] for k in _TEXT_KEYS if item.get(k)}
    attrs: Dict[str, str] = {}
    for key, value in item.items():
        if not isinstance(value, str) or not value:
            continue
        if key in _ATTR_NAMES:
            attrs[_ATTR_NAMES[key]] = value[:_FIELD_MAX]
        elif key.startswith("data_"):
            attrs["data-" + key[5:].replace("_", "-")] = value[:_FIELD_MAX]
    if attrs:
        fp["attrs"] = dict(list(attrs.items())[:40])
    frame = frame or item.get("frame") or ""
    if frame:
        fp["frame"] = str(frame)[:_FIELD_MAX]
    box = item.get("box")
    if isinstance(box, dict) and all(isinstance(box.get(k), (int, float)) for k in ("x", "y", "width", "height")):
        fp["box"] = {"x": box["x"], "y": box["y"], "w": box["width"], "h": box["height"]}
    return fp


def page_path(url: str) -> str:
    """The URL's path only: a query or fragment can carry a token."""
    try:
        return (urlsplit(url).path or "/")[:200]
    except ValueError:
        return "/"


# ---- the file --------------------------------------------------------------------------------------------------------
def load_store(path: Path) -> Dict[str, Any]:
    """The fingerprint file's content ({'version', 'entries'}), an empty store when it is missing or unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("entries"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": VERSION, "entries": {}}


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def ensure_ignore(directory: Path, env: Optional[Dict[str, str]] = None) -> None:
    """Write `.heal/.gitignore` containing `*` unless committing the cache was opted into."""
    env = env if env is not None else os.environ
    if env.get("HEAL_FINGERPRINTS_COMMIT", "").lower() == "on":
        return
    ignore = directory / ".gitignore"
    if not ignore.exists():
        directory.mkdir(parents=True, exist_ok=True)
        _atomic_write(ignore, "*\n")


def merge_into(root: Path, records: Dict[str, Dict[str, Any]], env: Optional[Dict[str, str]] = None) -> bool:
    """Merge `records` into the fingerprint file atomically, under a lock. True when the file changed."""
    directory = heal_dir(root, env)
    directory.mkdir(parents=True, exist_ok=True)
    ensure_ignore(directory, env)
    target = directory / "fingerprints.json"
    with open(directory / ".lock", "a") as lock:
        if fcntl is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            store = load_store(target)
            changed = False
            for key, entry in records.items():
                if store["entries"].get(key) != entry:
                    store["entries"][key] = entry
                    changed = True
            if changed:
                store["version"] = VERSION
                _atomic_write(target, json.dumps(store, indent=1, sort_keys=True) + "\n")
            return changed
        finally:
            if fcntl is not None:
                fcntl.flock(lock, fcntl.LOCK_UN)


def last_pass_for(store: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    """The request's `last_pass` for a locator key: its fingerprint, the other elements recorded on the same page, and
    the page language. None when nothing was recorded for the key."""
    entry = store.get("entries", {}).get(key)
    if not isinstance(entry, dict) or not isinstance(entry.get("fingerprint"), dict):
        return None
    neighbours: List[Dict[str, Any]] = []
    for other_key, other in sorted(store["entries"].items()):
        if other_key != key and isinstance(other, dict) and other.get("page") == entry.get("page") \
                and isinstance(other.get("fingerprint"), dict):
            neighbours.append(other["fingerprint"])
    out: Dict[str, Any] = {"fingerprint": entry["fingerprint"], "neighbours": neighbours[:MAX_NEIGHBOURS]}
    if entry.get("language"):
        out["language"] = entry["language"]
    return out


# ---- recording (the live part) ---------------------------------------------------------------------------------------
class Recorder:
    """Pending fingerprints of the test that is running, and the commit of them when it ends clean."""

    def __init__(self, root: Optional[Path] = None, env: Optional[Dict[str, str]] = None, probe=None):
        self.root = root or Path.cwd()
        self.env = env if env is not None else os.environ
        self.roots = source_roots(self.env)
        self.pending: Dict[str, Dict[str, Any]] = {}
        self.item: Any = None
        self.outcomes: Dict[str, str] = {}
        self._probe = probe
        self._probe_failed = False

    def probe_script(self) -> Optional[str]:
        """The service's probe script: fetched once, cached in .heal/probe.js, read back from there when offline."""
        if self._probe is not None or self._probe_failed:
            return self._probe
        cache = heal_dir(self.root, self.env) / "probe.js"
        try:
            from utils.heal_client import HealSettings, ServiceClient
            settings = HealSettings.from_env(self.env)
            if not settings.url:
                raise RuntimeError("HEAL_SERVICE_URL is not set")
            self._probe = ServiceClient(settings.url, settings.token).probe_js()
            ensure_ignore(cache.parent, self.env)
            cache.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(cache, self._probe)
        except Exception:
            try:
                self._probe = cache.read_text(encoding="utf-8")
            except OSError:
                self._probe_failed = True
        return self._probe

    def start_test(self, item: Any) -> None:
        self.item, self.pending, self.outcomes = item, {}, {}

    async def record(self, locator: Any) -> None:
        """Record what `locator` (about to be acted on) hits, once per acting line per test. Never raises."""
        key = None
        try:
            site = call_site(self.root, self.roots, depth=1)
            probe = self.probe_script() if site else None
            if not site or not probe:
                return
            key = call_key(site[0], site[2])
            if key in self.pending:
                return
            self.pending[key] = {}                       # claim the key first: a second action on this line is skipped
            data = await locator.evaluate(probe, timeout=2000)
            items = data.get("items") or []
            if len(items) != 1:
                self.pending.pop(key, None)
                return
            frame = await locator.evaluate(
                "e => { const f = e.ownerDocument.defaultView.frameElement;"
                " return f ? (f.getAttribute('name') || f.id || 'iframe') : ''; }", timeout=2000)
            meta = data.get("page") or {}
            language = (meta.get("lang") or meta.get("browser_lang") or "").split("-", 1)[0].lower()
            self.pending[key] = {"file": site[0], "text": normalize_line(site[2]), "page": page_path(meta.get("path") or "/"),
                                 "language": language, "fingerprint": item_to_fingerprint(items[0], frame or "")}
        except Exception:
            if key is not None:
                self.pending.pop(key, None)

    def clean(self) -> bool:
        """True when the test that just ended was clean green: passed once, no rerun, not flaky, not unstable."""
        item = self.item
        if item is None or any(self.outcomes.get(w) != "passed" for w in ("setup", "call", "teardown")):
            return False
        if getattr(item, "execution_count", 1) > 1 or item.get_closest_marker("flaky") is not None:
            return False
        try:
            from utils.stability_index import DEFAULT_THRESHOLD, get_stability
            return get_stability(item.nodeid) >= DEFAULT_THRESHOLD
        except Exception:
            return True

    def finish_test(self) -> bool:
        """Write the pending fingerprints when the test was clean green; drop them otherwise. True when written."""
        records = {k: v for k, v in self.pending.items() if v}
        clean = self.clean()
        self.pending = {}
        if not (clean and records):
            return False
        try:
            return merge_into(self.root, records, self.env)
        except OSError:
            return False


_RECORDER: Optional[Recorder] = None


def _install(recorder: Recorder) -> None:
    """Wrap the acting methods of Playwright's async Locator so each records its element first."""
    from playwright.async_api import Locator

    def wrap(name: str, original: Any) -> Any:
        async def acting(self: Any, *args: Any, **kwargs: Any) -> Any:
            await recorder.record(self)
            return await original(self, *args, **kwargs)
        acting.__name__ = getattr(original, "__name__", name)
        acting._heal_wrapped = True                      # type: ignore[attr-defined]
        return acting

    for name in ACTIONS:
        original = getattr(Locator, name, None)
        if original is not None and not getattr(original, "_heal_wrapped", False):
            setattr(Locator, name, wrap(name, original))


# ---- pytest hooks (registered through `pytest_plugins` in conftest.py) -------------------------------------------------
def pytest_configure(config: Any) -> None:
    global _RECORDER
    if enabled():
        _RECORDER = Recorder()
        try:
            _install(_RECORDER)
        except Exception:
            _RECORDER = None


def pytest_runtest_setup(item: Any) -> None:
    if _RECORDER is not None:
        _RECORDER.start_test(item)


def pytest_runtest_logreport(report: Any) -> None:
    if _RECORDER is None:
        return
    _RECORDER.outcomes[report.when] = "rerun" if getattr(report, "rerun", False) else report.outcome
    if report.when == "teardown":
        _RECORDER.finish_test()
