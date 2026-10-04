"""
===============================================================================
Playwright Browser Configuration and Page Fixture with Auto AI Healing
===============================================================================

This module provides the core Playwright browser configuration and page fixture
for automated testing across multiple browsers (Chromium, Firefox, WebKit).
It handles browser selection, headless mode configuration, and provides a
reusable async page fixture for all test modules.

NEW: Automatic AI healing is applied to ALL tests without needing decorators!
NEW: Automatically starts Ollama service if not running!
NEW: Automatically loads and warms up the specified model if not available!

Features:
    ✓ Multi-browser support (Chromium, Firefox, WebKit) via environment variables
    ✓ Configurable headless/headed mode for debugging and CI/CD environments
    ✓ Centralized browser options management through settings configuration
    ✓ Automatic browser cleanup after test execution
    ✓ Runtime browser selection without code changes
    ✓ AUTOMATIC AI healing for all test failures (no decorators needed!)
    ✓ Auto-starts Ollama service if not running
    ✓ Auto-loads and warms up specified model if not available
    ✓ Configurable Ollama host and model via environment variables
    ✓ Thread-safe for parallel test execution

Environment Variables:
    BROWSER: Specifies which browser to use (chromium|firefox|webkit)
    HEADLESS: Controls headless mode (true|false)
    OLLAMA_HOST: Ollama server URL (default: http://localhost:11434)
    OLLAMA_MODEL: Model to use for AI healing (default: qwen3:8b)

Usage Examples:
    # Run tests with default browser and AI healing
    pytest

    # Run tests with specific browser, retries, and custom Ollama settings
    BROWSER=firefox OLLAMA_MODEL=llama3.2:3b pytest --reruns 3
    OLLAMA_HOST=http://remote-server:11434 pytest --reruns 2

    # Run tests in headed mode for debugging
    HEADLESS=false pytest

Fixture Usage:
    @pytest.mark.asyncio
    async def test_example(page):
        await page.goto("https://example.com")
        # Test implementation here...
        # AI healing will automatically capture context on failure!

Dependencies:
    - playwright.async_api: Async Playwright API
    - pytest_asyncio: Async test support
    - config.settings: Application configuration management
    - utils.ai_healing: AI healing service
    - requests: For Ollama service health checks

Author: PMAC
Date: [2025-07-29]
===============================================================================
"""

import os
import re
import json
import time
import allure
import pytest
import pytest_asyncio
from config.settings import settings
from playwright.async_api import Locator, TimeoutError as PlaywrightTimeoutError
import threading
from collections import defaultdict
import asyncio
from utils.ai_healing import get_ollama_service, find_page_object, ensure_ollama_ready
from utils.browserstack import is_browserstack_enabled
from utils.debug import debug_print
from playwright.async_api import async_playwright
from utils.jira_client import get_jira_client, extract_ticket_id, JiraTestResult
from utils.test_observability import (
    get_observability_collector,
    TestMetric,
    categorize_error,
)

# Import the visual regression fixture
from utils.visual_regression import visual_regression

# Import the api mocking fixture
from utils.network_mocking import api_mocker

# Data setup / teardown fixtures
from utils.data_seeding import cleanup, session_cleanup, api_seed, db_seed

# QA quick-wins integrations
from pathlib import Path
from utils.api_capture import APICapture
from utils.zap_integration import ZAPIntegration
from utils.stability_index import record_result, get_unstable_tests

# Pytest fixtures (prevents auto-removal)
pytest_fixtures = [
    visual_regression, api_mocker, cleanup, session_cleanup, api_seed, db_seed
]

# Thread-safe dictionary and lock for tracking test failure counts
_ai_healing_fail_counts = defaultdict(int)
_ai_healing_lock = threading.Lock()

ollama_service = get_ollama_service()

# OWASP ZAP passive-scan integration (disabled unless ZAP_ENABLED=true)
zap = ZAPIntegration()


class ElementNotFoundException(Exception):
    """
    Custom exception raised when a Playwright Locator times out waiting for an element.
    This helps AI healing to detect element-not-found scenarios explicitly.
    """

    pass


# ------------------------------------------------------------------------------
# Function: get_selector
# ------------------------------------------------------------------------------


def get_selector(locator):
    """
    Safely retrieve the selector string from a Playwright Locator object.
    Falls back to the string representation if the private _selector attribute is missing.

    Args:
        locator (Locator): Playwright Locator instance.

    Returns:
        str: Selector string or fallback string representation.
    """
    return getattr(locator, "_selector", repr(locator))


# ------------------------------------------------------------------------------
# Function: patched_wait_for
# ------------------------------------------------------------------------------

_original_wait_for = Locator.wait_for


async def patched_wait_for(self, state="visible", timeout=None):
    """
    Monkey-patched version of Locator.wait_for that raises ElementNotFoundException
    instead of Playwright's TimeoutError when the element is not found within timeout.

    Args:
        state (str): The state to wait for (default: "visible").
        timeout (int): Timeout in milliseconds.

    Raises:
        ElementNotFoundException: If the element is not found within the timeout.

    Returns:
        The result of the original wait_for method if successful.
    """
    try:
        return await _original_wait_for(self, state=state, timeout=timeout)
    except PlaywrightTimeoutError:
        selector = get_selector(self)
        raise ElementNotFoundException(
            f"Element '{selector}' not found after waiting for state '{state}'"
        )


Locator.wait_for = patched_wait_for

# ------------------------------------------------------------------------------
# Function: patched_click
# ------------------------------------------------------------------------------

_original_click = Locator.click


async def patched_click(self, *args, timeout=None, **kwargs):
    """
    Monkey-patched version of Locator.click that raises ElementNotFoundException
    instead of Playwright's TimeoutError when the element is not clickable within timeout.

    Args:
        *args: Positional arguments for click.
        timeout (int): Timeout in milliseconds.
        **kwargs: Keyword arguments for click.

    Raises:
        ElementNotFoundException: If the element is not clickable within the timeout.

    Returns:
        The result of the original click method if successful.
    """
    try:
        return await _original_click(self, *args, timeout=timeout, **kwargs)
    except PlaywrightTimeoutError:
        selector = get_selector(self)
        raise ElementNotFoundException(
            f"Element '{selector}' not found (click timeout after {timeout}ms)"
        )


Locator.click = patched_click

# ------------------------------------------------------------------------------
# Function: patched_fill
# ------------------------------------------------------------------------------

_original_fill = Locator.fill


async def patched_fill(self, *args, timeout=None, **kwargs):
    """
    Monkey-patched version of Locator.fill that raises ElementNotFoundException
    instead of Playwright's TimeoutError when the element is not fillable within timeout.

    Args:
        *args: Positional arguments for fill.
        timeout (int): Timeout in milliseconds.
        **kwargs: Keyword arguments for fill.

    Raises:
        ElementNotFoundException: If the element is not fillable within the timeout.

    Returns:
        The result of the original fill method if successful.
    """
    try:
        return await _original_fill(self, *args, timeout=timeout, **kwargs)
    except PlaywrightTimeoutError:
        selector = get_selector(self)
        raise ElementNotFoundException(
            f"Element '{selector}' not found (fill timeout after {timeout}ms)"
        )


Locator.fill = patched_fill

# ------------------------------------------------------------------------------
# Standard artifacts: pytest-playwright style --tracing / --screenshot options
# (registered by pytest-playwright, set in pytest.ini) honored by our own page
# fixture. Output goes under --output (default results/artifacts).
# ------------------------------------------------------------------------------


def _option(request, name, default="off"):
    try:
        return request.config.getoption(name) or default
    except ValueError:
        return default


def _tracing_mode(request):
    return _option(request, "--tracing")


def _test_failed(request):
    rep = getattr(request.node, "rep_call", None)
    return bool(rep and rep.failed)


def _artifact_path(request, suffix):
    out = Path(_option(request, "--output", "results/artifacts"))
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.nodeid)
    out.mkdir(parents=True, exist_ok=True)
    return out / f"{safe}{suffix}"


async def _save_screenshot(request, page, failed):
    mode = _option(request, "--screenshot")
    if mode == "on" or (mode == "only-on-failure" and failed):
        try:
            await page.screenshot(path=str(_artifact_path(request, ".png")), full_page=True)
        except Exception as e:
            print(f"Could not save screenshot: {e}")


async def _save_trace(request, context, mode, failed):
    if mode == "off":
        return
    keep = mode == "on" or (mode == "retain-on-failure" and failed)
    try:
        if keep:
            await context.tracing.stop(path=str(_artifact_path(request, ".trace.zip")))
        else:
            await context.tracing.stop()
    except Exception as e:
        print(f"Could not save trace: {e}")


# ------------------------------------------------------------------------------
# Fixture: page
# ------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def page(request):
    """
    Async pytest fixture that launches a Playwright browser page based on environment
    variables or settings configuration. Supports Chromium, Firefox, and WebKit.
    Uses BrowserStack if BROWSERSTACK=true in environment.

    Yields:
        Page: An instance of Playwright's Page object for test use.

    Raises:
        ValueError: If an unsupported browser name is specified.
    """
    if is_browserstack_enabled():
        caps = {
            "browser": "chrome",
            "browser_version": "latest",
            "os": "osx",
            "os_version": "sonoma",
            "name": "Playwright Test",
            "build": "playwright-python-build-1",
            "browserstack.username": os.getenv("BROWSERSTACK_USERNAME"),
            "browserstack.accessKey": os.getenv("BROWSERSTACK_ACCESS_KEY"),
        }
        ws_endpoint = f"wss://cdp.browserstack.com/playwright?caps={json.dumps(caps)}"
        async with async_playwright() as p:
            browser = await p.chromium.connect(ws_endpoint)
            context = await browser.new_context()
            page = await context.new_page()
            print("\n Using BrowserStack cloud browser")
            api_capture = APICapture()
            page.on("request", api_capture.on_request)
            page.on("response", api_capture.on_response)
            page._api_capture = api_capture
            yield page
            await browser.close()
    else:
        # ...existing local browser logic...
        async with async_playwright() as p:
            browser_name = os.getenv("BROWSER", settings.BROWSER).lower()
            headless = os.getenv("HEADLESS", str(settings.HEADLESS)).lower() == "true"
            browser_options = settings.get_browser_options()
            browser_options["headless"] = headless
            # Route traffic through OWASP ZAP if enabled and running
            if zap.enabled and zap.is_running():
                browser_options.update(zap.get_browser_proxy_config())
                print(f"\nZAP proxy enabled: {zap.proxy_url}")
            if browser_name == "chromium":
                browser = await p.chromium.launch(**browser_options)
            elif browser_name == "firefox":
                browser = await p.firefox.launch(**browser_options)
            elif browser_name == "webkit":
                browser = await p.webkit.launch(**browser_options)
            else:
                raise ValueError(f"Unsupported BROWSER value: {browser_name}")
            context = await browser.new_context()
            tracing_mode = _tracing_mode(request)
            if tracing_mode != "off":
                await context.tracing.start(screenshots=True, snapshots=True, sources=True)
            page = await context.new_page()
            print(f"\n Using {browser_name} browser (headless={headless})")
            api_capture = APICapture()
            page.on("request", api_capture.on_request)
            page.on("response", api_capture.on_response)
            page._api_capture = api_capture
            yield page
            failed = _test_failed(request)
            await _save_screenshot(request, page, failed)
            await _save_trace(request, context, tracing_mode, failed)
            await browser.close()


# ------------------------------------------------------------------------------
# Hook: pytest_runtest_makereport
# ------------------------------------------------------------------------------
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Hook that runs after each test phase (setup, call, teardown).
    Automatically captures context for AI healing on ANY test failure.
    Triggers AI healing only on final failure (after all retries).
    Thread-safe for parallel test runs.

    NO DECORATORS NEEDED - this applies to ALL tests automatically!
    """
    outcome = yield
    rep = outcome.get_result()

    # Record the phase result for fixtures (trace/screenshot-on-failure) even
    # when AI healing is disabled.
    setattr(item, "rep_" + rep.when, rep)

    # Skip all AI healing logic if disabled
    if not ollama_service.enabled:
        return

    debug_print(
        f"DEBUG: rep.when={rep.when}, rep.failed={rep.failed}, item={item.nodeid}"
    )

    setattr(item, "rep_" + rep.when, rep)

    if rep.when == "call" and rep.failed:
        test_key = item.nodeid
        max_reruns = item.config.getoption("reruns") or 0

        # Increment fail count in a thread-safe way
        with _ai_healing_lock:
            _ai_healing_fail_counts[test_key] += 1
            fail_count = _ai_healing_fail_counts[test_key]

        debug_print(
            f"DEBUG: {test_key} fail_count={fail_count} (max_reruns={max_reruns})"
        )

        # Capture context on EVERY failure (for screenshot, DOM, etc.)
        page = find_page_object(item)
        error_message = str(call.excinfo.value) if call.excinfo else "Unknown error"
        screenshot_path = None

        # Attach captured API requests/responses on failure (QA-19)
        if page is not None and hasattr(page, "_api_capture"):
            api_data = page._api_capture.to_json()
            if api_data and api_data != "[]":
                allure.attach(
                    api_data,
                    name=f"API Requests: {item.name}",
                    attachment_type=allure.attachment_type.JSON,
                )

        # Use async capture_failure_context for full context (including DOM)
        if page:
            try:
                context, screenshot_path = asyncio.get_event_loop().run_until_complete(
                    ollama_service.capture_failure_context(
                        page,
                        error_message,
                        item.name,
                        getattr(item.function, "__func__", None),
                    )
                )
            except Exception as e:
                print(f"🧠 Error capturing failure context: {e}")
                context = {
                    "test_name": item.name,
                    "error_message": error_message,
                    "error_type": type(call.excinfo.value).__name__
                    if call.excinfo
                    else "Unknown",
                    "test_docstring": getattr(
                        getattr(item.function, "__func__", None), "__doc__", ""
                    ),
                    "capture_error": str(e),
                    "dom": f"DOM not available due to error: {e}",
                }
        else:
            context = {
                "test_name": item.name,
                "error_message": error_message,
                "error_type": type(call.excinfo.value).__name__
                if call.excinfo
                else "Unknown",
                "test_docstring": getattr(
                    getattr(item.function, "__func__", None), "__doc__", ""
                ),
                "capture_error": "No page object found",
                "dom": "DOM not available: No page object found",
            }

        # Try to get the original test code
        original_test_code = ""
        try:
            test_file = item.fspath
            with open(test_file, "r") as f:
                original_test_code = f.read()
        except Exception as e:
            print(f"Warning: Could not read test file: {e}")

        # Store context for later AI healing
        if not hasattr(ollama_service, "_pending_contexts"):
            ollama_service._pending_contexts = {}
        ollama_service._pending_contexts[test_key] = {
            "test_name": item.name,
            "context": context,
            "original_test_code": original_test_code,
            "screenshot_path": screenshot_path,
        }

        # This duplicates code in screenshot_decorator, but only runs if AI healing is on
        if screenshot_path and os.path.exists(screenshot_path):
            with open(screenshot_path, "rb") as image_file:
                allure.attach(
                    image_file.read(),
                    name=f"AI Healing Screenshot: {item.name}",
                    attachment_type=allure.attachment_type.PNG,
                )

        # Only trigger AI healing on the final failure
        if fail_count > max_reruns:
            print(f"\n🧠 Final failure detected for {item.name}, triggering AI healing")
            if hasattr(ollama_service, "_pending_contexts"):
                context_data = ollama_service._pending_contexts.get(test_key)
                if not context_data:
                    context_data = ollama_service._pending_contexts.get(item.name)
                if context_data and ollama_service.enabled:
                    if not ensure_ollama_ready():
                        print(
                            "🧠 AI healing skipped - Ollama service or model unavailable"
                        )
                        return
                    try:
                        ai_response = ollama_service.call_ollama_healing(
                            context_data["context"],
                            context_data["original_test_code"],
                            context_data["screenshot_path"],
                        )
                        if ai_response:
                            asyncio.run(
                                ollama_service.generate_healing_report(
                                    context_data["test_name"],
                                    ai_response,
                                    context_data["context"],
                                )
                            )
                        else:
                            print(f"🧠 Ollama analysis failed for {item.name}")
                        # Clean up
                        if test_key in ollama_service._pending_contexts:
                            del ollama_service._pending_contexts[test_key]
                        if item.name in ollama_service._pending_contexts:
                            del ollama_service._pending_contexts[item.name]
                    except Exception as e:
                        print(f"🧠 AI healing hook failed: {e}")
                else:
                    if not context_data:
                        print(f"🧠 No context data found for {item.name}")
                    if not ollama_service.enabled:
                        print(f"🧠 AI healing disabled for {item.name}")
            else:
                print("🧠 No pending contexts found")
            # Clean up fail count
            with _ai_healing_lock:
                if test_key in _ai_healing_fail_counts:
                    del _ai_healing_fail_counts[test_key]
        else:
            print(
                f"🔄 Test {item.name} will be retried (attempt {fail_count}), skipping AI healing"
            )


# ------------------------------------------------------------------------------
# Jira + Observability singletons
# ------------------------------------------------------------------------------

jira_client = get_jira_client()
observability_collector = get_observability_collector()

_test_start_times: dict[str, float] = {}
_observability_retry_counts: dict[str, int] = defaultdict(int)

# TestReport objects don't carry the pytest config, so capture it at startup
# for use in pytest_runtest_logreport.
_pytest_config = None


# Marks pytest itself (or common plugins) provides - never auto-registered.
_BUILTIN_MARKS = {
    "parametrize", "skip", "skipif", "xfail", "usefixtures", "filterwarnings",
    "asyncio", "flaky", "timeout", "tryfirst", "trylast",
}
_MARK_USE = re.compile(r"pytest\.mark\.([A-Za-z_][A-Za-z0-9_]*)")


def _register_used_markers(config):
    """
    Register every ``@pytest.mark.<name>`` found in the test paths so arbitrary
    FEATURE markers (login, cart, ...) work with ``pytest -m <name>`` and
    ``-m "smoke and cart"`` without PytestUnknownMarkWarning. Standard markers
    stay documented in pytest.ini; this only adds the ones that are missing.
    """
    known = {
        line.split(":", 1)[0].split("(", 1)[0].strip()
        for line in config.getini("markers")
    }
    roots = [Path(str(a).split("::")[0]) for a in config.args if a]
    roots += [config.rootpath / p for p in config.getini("testpaths")]
    for root in roots:
        root = root if root.is_absolute() else config.rootpath / root
        files = [root] if root.is_file() else root.rglob("*.py") if root.is_dir() else []
        for f in files:
            try:
                names = _MARK_USE.findall(f.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            for name in set(names) - known - _BUILTIN_MARKS:
                config.addinivalue_line("markers", f"{name}: feature marker (auto-registered)")
                known.add(name)


def pytest_configure(config):
    global _pytest_config
    _pytest_config = config
    _register_used_markers(config)


def _get_test_tags(report):
    """Return the registered marker names applied to this test."""
    if _pytest_config is None:
        return []
    registered = {
        line.split(":", 1)[0].split("(", 1)[0].strip()
        for line in _pytest_config.getini("markers")
    }
    return sorted(registered.intersection(report.keywords))


# ------------------------------------------------------------------------------
# Hook: pytest_runtest_setup — track test start time
# ------------------------------------------------------------------------------


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    _test_start_times[item.nodeid] = time.time()


# ------------------------------------------------------------------------------
# Hook: pytest_runtest_logreport — Jira reporting + observability
# ------------------------------------------------------------------------------


@pytest.hookimpl(trylast=True)
def pytest_runtest_logreport(report):
    if report.when != "call":
        return

    nodeid = report.nodeid

    # Record every call-phase result for the flaky-test stability index (QA-04)
    record_result(nodeid, report.passed)

    if report.failed:
        _observability_retry_counts[nodeid] += 1

    max_reruns = 0
    if _pytest_config is not None:
        max_reruns = _pytest_config.getoption("reruns", default=0) or 0

    is_final = (
        report.passed
        or report.skipped
        or _observability_retry_counts.get(nodeid, 0) > max_reruns
    )

    if not is_final:
        return

    duration_ms = int((time.time() - _test_start_times.get(nodeid, time.time())) * 1000)
    browser = os.getenv("BROWSER", settings.BROWSER)

    # --- Observability ---
    if observability_collector.enabled:
        error_msg = str(report.longrepr) if report.failed else None
        metric = TestMetric(
            test_id=nodeid,
            test_name=report.head_line
            if hasattr(report, "head_line")
            else nodeid.split("::")[-1],
            suite="::".join(nodeid.split("::")[:-1]),
            status="passed"
            if report.passed
            else ("skipped" if report.skipped else "failed"),
            duration_ms=duration_ms,
            retry_count=_observability_retry_counts.get(nodeid, 0),
            browser=browser,
            error_category=categorize_error(error_msg),
            tags=_get_test_tags(report),
        )
        observability_collector.record(metric)

    # --- Jira ---
    if jira_client.enabled:
        ticket_id = extract_ticket_id(nodeid)
        if ticket_id:
            status = (
                "passed"
                if report.passed
                else ("skipped" if report.skipped else "failed")
            )
            result = JiraTestResult(
                ticket_id=ticket_id,
                test_name=nodeid.split("::")[-1],
                status=status,
                duration_ms=duration_ms,
                error_message=str(report.longrepr)[:2000] if report.failed else None,
                test_file=nodeid.split("::")[0],
            )
            try:
                jira_client.report_test_result(result)
            except Exception as e:
                print(f"[Jira] Failed to report {ticket_id}: {e}")


# ------------------------------------------------------------------------------
# Hook: pytest_sessionfinish — write observability report
# ------------------------------------------------------------------------------


def pytest_sessionfinish(session, exitstatus):
    if observability_collector.enabled:
        observability_collector.write_report()
        observability_collector.print_summary()


# ------------------------------------------------------------------------------
# Hook: pytest_collection_modifyitems — quarantine unstable tests (QA-04)
# ------------------------------------------------------------------------------


def pytest_collection_modifyitems(config, items):
    """Quarantine flaky tests: they still run but are xfail'd so they don't block CI."""
    threshold = float(os.getenv("STABILITY_THRESHOLD", "0.7"))
    unstable = get_unstable_tests(threshold)
    if not unstable:
        return
    for item in items:
        if item.nodeid in unstable:
            item.add_marker(
                pytest.mark.xfail(
                    reason=f"Quarantined: stability below {threshold}",
                    strict=False,
                )
            )


# ------------------------------------------------------------------------------
# Fixture: zap_report_on_finish — write OWASP ZAP passive-scan report (QA-24)
# ------------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def zap_report_on_finish():
    """Generate a ZAP security report after all tests complete, if ZAP is active."""
    yield
    if zap.enabled and zap.is_running():
        report = zap.generate_report()
        report_path = Path("test_artifacts/zap_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report)
        print(f"\nZAP report saved: {report_path}")
        alerts = zap.get_alerts_summary()
        if alerts.get("High", 0) > 0:
            print(f"WARNING: ZAP found {alerts['High']} HIGH severity issues!")
