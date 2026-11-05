"""
===============================================================================
Heal Service Client (evidence out, patch in, nothing about models)
===============================================================================
Talks to the heal service (HEAL_SERVICE_URL) on behalf of `scripts/heal.py`. It knows HTTP, the browser, git-tracked source
files and the framework's own safety checks, and nothing about models: no model URL, no model name, no prompt and no parsing
of a model reply live in this repository. The service picks the element and writes the locator; this client only
    - builds the request: the stack files under the source roots (capped, with sha256), the probe's element inventory of the
      reopened failing route, the aria snapshot, the language signals, the last green run's fingerprint and its neighbours
    - checks every candidate in the live page BEFORE touching a file: the locator must match exactly one element and that
      element must be the one the service expects (the probe's `only` mode describes it; no code from the service is ever
      evaluated, the locator expression is walked and only approved Playwright calls with literal arguments are run)
    - applies a patch only when its base hash is the file's current hash, the file is one the client sent and sits under the
      source roots, the span holds exactly `from`, and `to` passes the locator validator (each language branch separately)
    - re-runs the exact test, keeps the edit only when the service confirms `healed`, reverts it otherwise, and reports every
      try to the service so it can move to the next candidate

Features:
    ✓ HealSettings: HEAL_SERVICE_URL, HEAL_SERVICE_TOKEN, HEAL_VISION (accepted; this client never sends a screenshot),
      HEAL_MASK (accepted, unused until vision), HEAL_TEST_ID_ATTRIBUTE, HEAL_SOURCE_ROOTS, HEAL_STORAGE_STATE, BASE_URL
    ✓ ServiceClient: capabilities, probe.js (fetched once), heal, result; every failure is a HealServiceError that names the
      status and the service's reason, never the request
    ✓ Language signals: <html lang>, the browser locale and the Content-Language header of the page load
    ✓ Patch safety refusals: stale base hash, file outside the source roots or never sent, span that does not hold `from`,
      overlapping spans, a replacement that fails validate_replacement, a branch set that does not match the code
    ✓ A service or browser error ends that heal as needs_human with the reason; it never crashes the run
    ✓ Language branches: the by_language helper (utils/heal_locale.py) is imported into a file that receives branch code
    ✓ Input values are never sent: the probe does not read them, and no cookie, storage state or screenshot leaves the client

Environment Variables:
    HEAL_SERVICE_URL: base URL of the heal service, for example http://localhost:8765
    HEAL_SERVICE_TOKEN: bearer token, when the service requires one
    HEAL_VISION: off | auto | on (accepted; screenshots are not captured by this client, so it is always off)
    HEAL_MASK: locators to mask in a screenshot (accepted, unused until vision)
    HEAL_TEST_ID_ATTRIBUTE: the project's test id attribute (default data-testid)
    HEAL_SOURCE_ROOTS: comma separated source roots (default pages,tests,utils)
    HEAL_STORAGE_STATE: Playwright storage-state file used to open the page as a signed-in user (never sent)
    BASE_URL: the app under test (default http://localhost:7080)

Author: PMAC
===============================================================================
"""
import ast
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx

from utils.heal_fingerprints import (call_key, last_pass_for, line_of, load_store, relative_under, source_roots)
from utils.heal_locale import page_language

LIMITS = {"files": 20, "file_bytes": 256 * 1024, "aria_chars": 256 * 1024}
HELPER = "by_language"
HELPER_IMPORT = "from utils.heal_locale import by_language"

# A replacement may only be a chain of these Playwright locator calls on the same receiver as the expression it replaces,
# with literal arguments.
ALLOWED_LOCATOR_METHODS = {
    "locator", "get_by_role", "get_by_label", "get_by_text", "get_by_placeholder",
    "get_by_test_id", "get_by_alt_text", "get_by_title", "first", "last", "nth", "filter",
}
_LANG_KEY = re.compile(r"^[a-z]{2,3}$")
_TRACE_LINE = re.compile(r"^\s*(\S+?\.py):(\d+)\b", re.M)


# ---- settings --------------------------------------------------------------------------------------------------------
@dataclass
class HealSettings:
    """What the client reads from the environment."""
    url: str = ""
    token: str = ""
    vision: str = "off"
    mask: List[str] = field(default_factory=list)
    test_id_attribute: str = "data-testid"
    roots: Tuple[str, ...] = ("pages", "tests", "utils")
    storage_state: Optional[str] = None
    base_url: str = "http://localhost:7080"

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "HealSettings":
        env = env if env is not None else os.environ
        attr = env.get("HEAL_TEST_ID_ATTRIBUTE", "data-testid").strip().lower()
        return cls(url=env.get("HEAL_SERVICE_URL", "").strip().rstrip("/"), token=env.get("HEAL_SERVICE_TOKEN", "").strip(),
                   vision=env.get("HEAL_VISION", "off").strip().lower() or "off",
                   mask=[m.strip() for m in env.get("HEAL_MASK", "").split(",") if m.strip()],
                   test_id_attribute=attr if re.fullmatch(r"[a-z][a-z0-9-]{0,63}", attr) else "data-testid",
                   roots=source_roots(env), storage_state=env.get("HEAL_STORAGE_STATE") or None,
                   base_url=env.get("BASE_URL", "http://localhost:7080"))


# ---- the service -----------------------------------------------------------------------------------------------------
class HealServiceError(Exception):
    """The service could not be reached or refused a call. The message names the status and reason, never the request."""


class ServiceClient:
    """The service's HTTP API. `http` may be any httpx.Client (a test passes one on a MockTransport or an ASGI app)."""

    def __init__(self, base_url: str, token: str = "", http: Optional[httpx.Client] = None, timeout: float = 200.0):
        self.base = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=timeout)
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._probe: Optional[str] = None

    def _call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> httpx.Response:
        try:
            resp = self.http.request(method, self.base + path, headers=self.headers,
                                     content=json.dumps(body).encode() if body is not None else None)
        except httpx.HTTPError as e:
            raise HealServiceError(f"the heal service could not be reached ({type(e).__name__})") from None
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail")
            except ValueError:
                detail = None
            raise HealServiceError(f"the heal service answered {resp.status_code}: " + str(detail or resp.reason_phrase)[:300])
        return resp

    def _json(self, resp: httpx.Response) -> Dict[str, Any]:
        try:
            data = resp.json()
        except ValueError:
            raise HealServiceError("the heal service sent a reply that is not JSON") from None
        if not isinstance(data, dict):
            raise HealServiceError("the heal service sent a reply that is not a JSON object")
        return data

    def capabilities(self) -> Dict[str, Any]:
        return self._json(self._call("GET", "/v1/capabilities"))

    def probe_js(self) -> str:
        """The in-page probe script, fetched once per client."""
        if self._probe is None:
            self._probe = self._call("GET", "/v1/probe.js").text
        return self._probe

    def heal(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self._json(self._call("POST", "/v1/heal", request))

    def result(self, heal_id: str, report: Dict[str, Any]) -> Dict[str, Any]:
        return self._json(self._call("POST", f"/v1/heals/{heal_id}/result", report))


# ---- the locator validator (a second check on everything the service sends) -------------------------------------------
def validate_replacement(proposed, original):
    """
    Return the replacement if it is a safe drop-in for ``original``, else None.
    Must be a single-line expression that is a chain of approved Playwright
    locator calls with literal arguments, rooted at the same receiver
    (``page`` / ``self.page``) as the original.
    """
    if not proposed or "\n" in proposed or ";" in proposed:
        return None
    try:
        tree = ast.parse(proposed, mode="eval").body
        original_tree = ast.parse(original, mode="eval").body
    except SyntaxError:
        return None

    def receiver(node):
        while isinstance(node, (ast.Call, ast.Attribute)):
            node = node.func if isinstance(node, ast.Call) else node.value
        return node

    def base_receiver(node):
        # the object the first locator method is called on, e.g. self.page
        chain = []
        while isinstance(node, (ast.Call, ast.Attribute)):
            chain.append(node)
            node = node.func if isinstance(node, ast.Call) else node.value
        for n in reversed(chain):
            if isinstance(n, ast.Attribute) and n.attr in ALLOWED_LOCATOR_METHODS:
                return ast.unparse(n.value)
        return None

    if not isinstance(tree, (ast.Call, ast.Attribute)) or not isinstance(receiver(tree), ast.Name):
        return None
    if base_receiver(tree) != base_receiver(original_tree):
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            # attribute access is allowed only for approved methods and the receiver chain
            if node.attr not in ALLOWED_LOCATOR_METHODS and ast.unparse(node) not in {"self.page"}:
                return None
        elif isinstance(node, ast.Call):
            for arg in [*node.args, *(k.value for k in node.keywords)]:
                if not isinstance(arg, ast.Constant):
                    return None
        elif not isinstance(node, (ast.Name, ast.Constant, ast.Load, ast.keyword)):
            return None
    return proposed


def _receiver_text(expr: str) -> Optional[str]:
    """The object the first locator method of `expr` is called on (`self.page`), or None."""
    try:
        node: Any = ast.parse(expr, mode="eval").body
    except SyntaxError:
        return None
    chain = []
    while isinstance(node, (ast.Call, ast.Attribute)):
        chain.append(node)
        node = node.func if isinstance(node, ast.Call) else node.value
    for n in reversed(chain):
        if isinstance(n, ast.Attribute) and n.attr in ALLOWED_LOCATOR_METHODS:
            return ast.unparse(n.value)
    return None


def _branch_dict(code: str) -> Optional[Tuple[str, Dict[str, str]]]:
    """(receiver, {language: code}) when `code` is `by_language(<receiver>, {"en": ..., "fr": ...})`, else None."""
    try:
        node = ast.parse(code, mode="eval").body
    except SyntaxError:
        return None
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == HELPER
            and len(node.args) == 2 and not node.keywords and isinstance(node.args[1], ast.Dict)):
        return None
    out: Dict[str, str] = {}
    for key, value in zip(node.args[1].keys, node.args[1].values):
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str) and _LANG_KEY.match(key.value)) \
                or key.value in out:
            return None
        out[key.value] = ast.unparse(value)
    return ast.unparse(node.args[0]), out


def check_replacement(to: str, original: str, branches: Optional[Dict[str, str]] = None,
                      exact_branches: bool = True) -> Optional[str]:
    """None when `to` may replace `original`, else the reason it may not.

    A plain locator must pass validate_replacement. Branch code (by_language(receiver, {...})) must name the same languages
    as `branches`, carry the same locator for each (`exact_branches`; a patch in another file has its own receiver), and
    EVERY branch must pass validate_replacement on its own."""
    if to == original:
        return "the replacement is identical to the failing locator"
    if "\n" in to or ";" in to:
        return "the replacement is not a single expression"
    if HELPER + "(" in to or branches:
        parsed = _branch_dict(to)
        if parsed is None or not branches:
            return "the replacement is not a by_language(receiver, {...}) call matching the candidate's branches"
        receiver, found = parsed
        if set(found) != set(branches):
            return "the languages in the code differ from the candidate's branches"
        if receiver != _receiver_text(original):
            return "the helper's receiver is not the receiver of the failing locator"
        for lang, code in found.items():
            if exact_branches and ast.unparse(ast.parse(branches[lang], mode="eval").body) != code:
                return f"the {lang} branch in the code differs from the candidate's branch"
            if validate_replacement(code, original) is None:
                return f"the {lang} branch is not a safe locator"
        return None
    return None if validate_replacement(to, original) is not None else "the replacement is not a safe locator expression"


def build_locator(page: Any, expression: str) -> Any:
    """The Playwright locator an approved expression stands for, built by walking its syntax tree: only the allowed
    locator methods, literal arguments, on `page` or `self.page`. Nothing is ever eval'd. None when it cannot be built."""
    try:
        node = ast.parse(expression, mode="eval").body
    except SyntaxError:
        return None

    def walk(n: Any) -> Any:
        if isinstance(n, ast.Call):
            f = n.func
            if not (isinstance(f, ast.Attribute) and f.attr in ALLOWED_LOCATOR_METHODS):
                raise ValueError("unsupported call")
            args = [a.value for a in n.args if isinstance(a, ast.Constant)]
            kwargs = {k.arg: k.value.value for k in n.keywords if k.arg and isinstance(k.value, ast.Constant)}
            if len(args) != len(n.args) or len(kwargs) != len(n.keywords):
                raise ValueError("non-literal argument")
            return getattr(walk(f.value), f.attr)(*args, **kwargs)
        if isinstance(n, ast.Attribute):
            if n.attr in ("first", "last"):
                return getattr(walk(n.value), n.attr)
            if ast.unparse(n) == "self.page":
                return page
            raise ValueError("unsupported attribute")
        if isinstance(n, ast.Name) and n.id == "page":
            return page
        raise ValueError("unsupported receiver")

    try:
        return walk(node)
    except (ValueError, AttributeError, TypeError):
        return None


# ---- the failure: stack, test id, source files, route ------------------------------------------------------------------
def stack_from_error(error: str, roots: Tuple[str, ...], root: Path) -> List[Dict[str, Any]]:
    """The traceback's frames under the source roots, innermost first: [{file, line}]. pytest prints outermost first."""
    seen, frames = set(), []
    for m in _TRACE_LINE.finditer(error or ""):
        rel = relative_under(m.group(1), root, roots)
        if rel and (rel, int(m.group(2))) not in seen:
            seen.add((rel, int(m.group(2))))
            frames.append({"file": rel, "line": int(m.group(2))})
    return frames[::-1]


def junit_test_id(classname: str, name: str, root: Path) -> str:
    """`tests/login/test_login.py::TestX::test_name` from a JUnit classname (dotted module path + classes) and name."""
    parts = (classname or "").split(".")
    for cut in range(len(parts), 0, -1):
        rel = "/".join(parts[:cut]) + ".py"
        if (root / rel).is_file():
            return "::".join([rel, *parts[cut:], name])
    return f"{classname}::{name}" if classname else name


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_text_file(root: Path, rel: str) -> Optional[Tuple[str, bytes]]:
    """(text, raw bytes) of a file inside `root`, newlines untouched, or None when it is missing or not UTF-8."""
    try:
        raw = (root / rel).read_bytes()
        return raw.decode("utf-8"), raw
    except (OSError, UnicodeDecodeError):
        return None


def collect_source(stack: List[Dict[str, Any]], roots: Tuple[str, ...], root: Path) -> List[Dict[str, str]]:
    """The files named in the failing stack that sit under the source roots, as {path, sha256, content}. At most 20 files,
    256 KB each; a file inside a symlink that leaves the repository is skipped."""
    files: List[Dict[str, str]] = []
    base = root.resolve()
    for rel in dict.fromkeys(f["file"] for f in stack):
        if len(files) >= LIMITS["files"] or not any(rel.startswith(r + "/") for r in roots):
            continue
        try:
            (root / rel).resolve().relative_to(base)
        except (ValueError, OSError):
            continue
        got = read_text_file(root, rel)
        if got and len(got[1]) <= LIMITS["file_bytes"]:
            files.append({"path": rel, "sha256": _sha(got[1]), "content": got[0]})
    return files


def route_from_source(content: str) -> str:
    """The page route a page object's `self.url = f"{BASE_URL}/path"` names; "/" when it names none."""
    m = re.search(r'self\.url\s*=\s*f?["\'][^"\']*BASE_URL\}?([^"\']*)["\']', content)
    return m.group(1) if m else "/"


def client_version(root: Path) -> str:
    try:
        return (root / "VERSION").read_text(encoding="utf-8").strip()[:50]
    except OSError:
        return ""


def build_request(failure: Dict[str, Any], files: List[Dict[str, str]], stack: List[Dict[str, Any]], page: Dict[str, Any],
                  settings: HealSettings, root: Path, last_pass: Optional[Dict[str, Any]] = None,
                  run_id: Optional[str] = None) -> Dict[str, Any]:
    """The POST /v1/heal body. `page` is a LivePage snapshot: path, language signals, inventory, aria, viewport.
    No screenshot is ever included (vision is off), and no input value: the inventory comes from the probe."""
    req: Dict[str, Any] = {
        "client": {"framework": "playwright-ai-framework", "language": "python", "version": client_version(root)},
        "test": {"id": junit_test_id(failure.get("classname", ""), failure["name"], root), "title": failure["name"][:500]},
        "failure": {"error": (failure.get("error") or "")[:100_000], "stack": stack},
        "source": {"roots": list(settings.roots), "files": files},
        "page": {"url": page["path"], "language": page["language"], "inventory": page["inventory"],
                 "inventory_more": page["more"], "viewport": page["viewport"], "screenshot": None},
        "options": {"vision": "off", "max_rounds": 3, "locale_branching": True},
        "test_id_attribute": settings.test_id_attribute,
        "run": {"id": run_id or uuid.uuid4().hex[:12]},
    }
    if page.get("aria") and len(page["aria"]) <= LIMITS["aria_chars"]:
        req["page"]["aria_snapshot"] = page["aria"]
    if last_pass:
        req["last_pass"] = last_pass
    repo = os.environ.get("HEAL_REPO")
    if repo:
        req["run"]["repo"] = repo[:200]
    return req


# ---- patch safety ------------------------------------------------------------------------------------------------------
class PatchRefused(Exception):
    """A patch the client will not apply. `fatal` means the service's evidence and the disk disagree (stale hash, wrong
    file, wrong span): the heal ends there. A replacement that is merely unsafe only rules this candidate out."""

    def __init__(self, reason: str, fatal: bool = False):
        super().__init__(reason)
        self.reason, self.fatal = reason, fatal


@dataclass
class PlannedFile:
    rel: str
    original: bytes
    new_text: str


def plan_patches(candidate: Dict[str, Any], sent: Dict[str, str], roots: Tuple[str, ...], root: Path) -> List[PlannedFile]:
    """Check every patch of a candidate (the main one and `also_patches`) and return the new content of each file touched,
    or raise PatchRefused. Nothing is written here."""
    patches = [candidate["patch"], *(candidate.get("also_patches") or [])]
    branches = candidate.get("branches") or None
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for i, p in enumerate(patches):
        rel = p.get("file", "")
        if not relative_under(rel, root, roots) or rel.startswith("/") or ".." in rel.split("/"):
            raise PatchRefused(f"{rel or 'a patch'} is not under the source roots", fatal=True)
        if rel not in sent:
            raise PatchRefused(f"{rel} was not one of the files sent to the service", fatal=True)
        why = check_replacement(p["to"], p["from"], branches, exact_branches=(i == 0))
        if why:
            raise PatchRefused(why)
        by_file.setdefault(rel, []).append(p)
    planned: List[PlannedFile] = []
    for rel, group in by_file.items():
        got = read_text_file(root, rel)
        if got is None:
            raise PatchRefused(f"{rel} cannot be read", fatal=True)
        text, raw = got
        digest = _sha(raw)
        spans = sorted(((p["span"]["start"], p["span"]["end"], p) for p in group), key=lambda t: t[0])
        for p in group:
            if p["base_sha256"].lower() != digest or sent[rel].lower() != digest:
                raise PatchRefused(f"{rel} changed since the service saw it (base hash differs)", fatal=True)
        end_prev = -1
        for start, end, p in spans:
            if not (0 <= start <= end <= len(text)) or start < end_prev or text[start:end] != p["from"]:
                raise PatchRefused(f"the span in {rel} does not hold the text the service expected", fatal=True)
            end_prev = end
        new = text
        for start, end, p in reversed(spans):
            new = new[:start] + p["to"] + new[end:]
        if HELPER + "(" in new and HELPER_IMPORT not in new and f"import {HELPER}" not in new:
            new = _with_helper_import(new)
        planned.append(PlannedFile(rel, raw, new))
    return planned


def _with_helper_import(source: str) -> str:
    """`source` with the by_language import added after its last top-level import (or after the module docstring)."""
    lines = source.splitlines(keepends=True)
    insert_at = 0
    try:
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                insert_at = node.end_lineno or insert_at
            elif insert_at == 0 and isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant):
                insert_at = node.end_lineno or 0                  # the module docstring
    except SyntaxError:
        pass
    newline = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    lines.insert(insert_at, HELPER_IMPORT + newline)
    return "".join(lines)


def write_files(root: Path, planned: List[PlannedFile]) -> None:
    for pf in planned:
        _replace(root / pf.rel, pf.new_text.encode("utf-8"))


def revert_files(root: Path, planned: List[PlannedFile]) -> None:
    for pf in planned:
        _replace(root / pf.rel, pf.original)


def _replace(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".heal-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


# ---- the live page ---------------------------------------------------------------------------------------------------
def _box_free(item: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in item.items() if k not in ("box", "frame", "shadow", "ref")}


def match_ref(inventory: List[Dict[str, Any]], facts: Dict[str, Any]) -> Optional[str]:
    """The inventory ref of the element the probe described in `facts`: an exact match on everything the probe listed, else
    one that ignores box, frame and shadow. None when no entry or several entries fit (the hit cannot be named)."""
    plain = {k: v for k, v in facts.items() if k != "ref"}
    exact = [e["ref"] for e in inventory if {k: v for k, v in e.items() if k != "ref"} == plain]
    if len(exact) == 1:
        return exact[0]
    loose = [e["ref"] for e in inventory if _box_free(e) == _box_free(facts)]
    return loose[0] if len(loose) == 1 else None


class LivePage:
    """A fresh Chromium on the failing route (HEAL_STORAGE_STATE when set). It stays open for the whole heal so each
    candidate can be checked on the same page the inventory came from. Never screenshots."""

    def __init__(self, settings: HealSettings, route: str, probe: str):
        self.settings, self.route, self.probe = settings, route or "/", probe
        self.inventory: List[Dict[str, Any]] = []
        self.language = ""
        self._p = self._browser = self.page = None

    def __enter__(self) -> "LivePage":
        from playwright.sync_api import sync_playwright
        self._p = sync_playwright().start()
        try:
            self._browser = self._p.chromium.launch()
            ctx = self._browser.new_context(
                base_url=self.settings.base_url,
                **({"storage_state": self.settings.storage_state} if self.settings.storage_state else {}))
            self.page = ctx.new_page()
            self._response = self.page.goto(self.route)
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *exc: Any) -> None:
        for closer in (getattr(self._browser, "close", None), getattr(self._p, "stop", None)):
            try:
                if closer:
                    closer()
            except Exception:
                pass

    def snapshot(self) -> Dict[str, Any]:
        """Run the probe on the page and read its aria snapshot: path, language signals, numbered inventory, viewport."""
        data = self.page.evaluate(self.probe)
        meta = data.get("page") or {}
        header = None
        try:
            header = self._response.headers.get("content-language") if self._response else None
        except Exception:
            pass
        self.inventory = [{"ref": f"e{i}", **item} for i, item in enumerate(data.get("items") or [])]
        self.language = page_language(meta.get("lang"), meta.get("browser_lang"), header)
        try:
            aria = self.page.locator("body").aria_snapshot()
        except Exception:
            aria = None
        view = meta.get("viewport") or {}
        return {"path": urlsplit(self.page.url).path or "/", "inventory": self.inventory, "more": int(data.get("more") or 0),
                "aria": aria, "viewport": {"w": view.get("width"), "h": view.get("height"), "dpr": meta.get("dpr")},
                "language": {"html_lang": meta.get("lang") or None, "browser_locale": meta.get("browser_lang") or None,
                             "content_language": header}}

    def check(self, expression: str) -> Tuple[Optional[int], Optional[str]]:
        """(match count, inventory ref of the one element hit). The ref is None unless the count is 1 and the element can
        be named; the count is None when the expression cannot be run here."""
        loc = build_locator(self.page, expression)
        if loc is None:
            return None, None
        count = loc.count()
        if count != 1:
            return count, None
        facts = (loc.evaluate(self.probe).get("items") or [None])[0]
        return 1, (match_ref(self.inventory, facts) if facts else None)


# ---- the heal loop ---------------------------------------------------------------------------------------------------
def _expression_for(candidate: Dict[str, Any], language: str) -> Optional[str]:
    """The locator expression to check live: the candidate's code, or for branch code the branch of the page's language."""
    branches = candidate.get("branches")
    if not branches:
        return candidate["code"]
    return branches.get(language) if language in branches else None


class Healer:
    """Heals one failing test at a time through the service. All collaborators are injected, so a test can drive the whole
    loop with a fake service and a fake page: `verify(test) -> bool` re-runs the exact test, `live_factory(route, probe)`
    opens the page."""

    def __init__(self, service: ServiceClient, settings: HealSettings, verify: Callable[[Dict[str, Any]], bool],
                 root: Optional[Path] = None, live_factory: Optional[Callable[[str, str], Any]] = None,
                 run_id: Optional[str] = None):
        self.service, self.settings, self.verify = service, settings, verify
        self.root = root or Path.cwd()
        self.live_factory = live_factory or (lambda route, probe: LivePage(settings, route, probe))
        self.run_id = run_id or uuid.uuid4().hex[:12]

    # one failure -> one decision
    def heal(self, failure: Dict[str, Any]) -> Dict[str, Any]:
        base = {"test": failure["name"]}
        try:
            return {**base, **self._heal(failure)}
        except HealServiceError as e:
            return {**base, "outcome": "needs_human", "reason": "service_error", "why": str(e)}
        except Exception as e:                                    # the browser, the disk: this heal ends, the run goes on
            return {**base, "outcome": "needs_human", "reason": "client_error",
                    "why": f"the heal client failed ({type(e).__name__}): {str(e)[:200]}"}

    def _heal(self, failure: Dict[str, Any]) -> Dict[str, Any]:
        roots = self.settings.roots
        stack = stack_from_error(failure.get("error", ""), roots, self.root)
        files = collect_source(stack, roots, self.root)
        sent = {f["path"]: f["sha256"] for f in files}
        last_pass = self._last_pass(stack)
        route = last_pass.pop("_page") if last_pass else None
        if route is None:
            route = route_from_source(files[0]["content"]) if files else "/"
        probe = self.service.probe_js()
        kept: List[PlannedFile] = []
        with self.live_factory(route, probe) as live:
            snap = live.snapshot()
            request = build_request(failure, files, stack, snap, self.settings, self.root, last_pass, self.run_id)
            resp = self.service.heal(request)
            while resp.get("status") == "try" and resp.get("candidate"):
                resp, kept = self._try(failure, resp, live, sent, live.language)
                if kept:
                    break
        return self._decision(resp, kept)

    def _last_pass(self, stack: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """The last green run's fingerprint of the failing line (with the page it was on), or None."""
        if not stack:
            return None
        top = stack[0]
        text = line_of(self.root, top["file"], top["line"])
        store = load_store(self.root / os.environ.get("HEAL_DIR", ".heal") / "fingerprints.json")
        key = call_key(top["file"], text)
        lp = last_pass_for(store, key) if text else None
        if lp is None:
            return None
        lp["_page"] = store["entries"][key].get("page") or "/"
        return lp

    def _try(self, failure: Dict[str, Any], resp: Dict[str, Any], live: Any, sent: Dict[str, str],
             language: str) -> Tuple[Dict[str, Any], List[PlannedFile]]:
        """One candidate: check it live, apply it, re-run the exact test, report. Returns the service's next answer and the
        files kept (non-empty only when the service confirmed `healed`)."""
        cand, heal_id = resp["candidate"], resp["heal_id"]
        expected = (cand.get("expect") or {}).get("ref")
        expression = _expression_for(cand, language)
        if expression is None:
            return self._report(heal_id, {"count": None, "error": "no branch for the page's language"}), []
        if not cand.get("branches") and check_replacement(expression, cand["patch"]["from"]):
            return self._report(heal_id, {"count": None, "error": "the locator is not a safe expression"}), []
        count, ref = live.check(expression)
        if count != 1 or ref != expected:                      # nothing has been edited yet
            report: Dict[str, Any] = {"count": count}
            if ref:
                report["hit"] = {"ref": ref}
            return self._report(heal_id, report), []
        try:
            planned = plan_patches(cand, sent, self.settings.roots, self.root)
        except PatchRefused as e:
            report = {"count": 1, "hit": {"ref": ref}, "test_outcome": "error",
                      "error": f"patch refused by the client: {e.reason}"[:500]}
            if not e.fatal:
                return self._report(heal_id, report), []
            try:
                self.service.result(heal_id, report)
            except HealServiceError:
                pass
            return {**resp, "status": "needs_human", "reason": "patch_refused",
                    "why": f"the client refused the patch: {e.reason}"}, []
        write_files(self.root, planned)
        try:
            passed = bool(self.verify(failure))
            if not passed:
                revert_files(self.root, planned)
            nxt = self._report(heal_id, {"count": 1, "hit": {"ref": ref},
                                         "test_outcome": "passed" if passed else "failed"})
        except BaseException:
            revert_files(self.root, planned)                   # a verify crash or a lost service: never keep the edit
            raise
        if passed and nxt.get("status") == "healed":
            return nxt, planned
        if passed:                                             # the service did not confirm it: do not keep it
            revert_files(self.root, planned)
        return nxt, []

    def _report(self, heal_id: str, report: Dict[str, Any]) -> Dict[str, Any]:
        return self.service.result(heal_id, report)

    @staticmethod
    def _decision(resp: Dict[str, Any], kept: List[PlannedFile]) -> Dict[str, Any]:
        usage = resp.get("usage") or {}
        out: Dict[str, Any] = {"heal_id": resp.get("heal_id"), "reason": resp.get("reason"), "why": resp.get("why"),
                               "rounds": resp.get("round"), "settled_at": resp.get("settled_at"),
                               "usage": {"calls": usage.get("calls", 0), "input_tokens": usage.get("input_tokens", 0),
                                         "output_tokens": usage.get("output_tokens", 0), "images": usage.get("images", 0)}}
        status = resp.get("status")
        if status == "healed" and kept and resp.get("candidate"):
            p = resp["candidate"]["patch"]
            out.update(outcome="healed", file=p["file"], to=p["to"], strategy=resp["candidate"].get("strategy"),
                       tier_movement=resp["candidate"].get("tier_movement"), why=resp["candidate"].get("why"),
                       files=[pf.rel for pf in kept])
            out["from"] = p["from"]
            out["source"] = f"heal service (settled at step {resp.get('settled_at')})"
        elif status == "not_drift":
            out["outcome"] = "not_drift"
        else:
            out["outcome"] = "needs_human"
            if status in ("try", "healed"):
                out["reason"] = out["reason"] or "unconfirmed"
                out["why"] = out["why"] or "the service did not confirm the heal"
        return out


def run_total(decisions: List[Dict[str, Any]]) -> Dict[str, int]:
    """Calls and tokens summed over every decision that carries usage."""
    total = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "images": 0}
    for d in decisions:
        for k in total:
            total[k] += int((d.get("usage") or {}).get(k, 0) or 0)
    return total


__all__ = ["HealSettings", "HealServiceError", "ServiceClient", "Healer", "LivePage", "PatchRefused", "build_locator",
           "build_request", "check_replacement", "collect_source", "match_ref", "plan_patches", "run_total",
           "stack_from_error", "junit_test_id", "validate_replacement"]
