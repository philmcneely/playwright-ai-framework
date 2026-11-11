"""
===============================================================================
Unit Tests: utils/heal_locale.py -- the by_language helper for healed copy-based locators
===============================================================================
The helper returns the locator of the page's language and the FIRST entry (the original copy) for any other language, never
raises on a page it cannot ask, and reads the language from <html lang>, then the browser locale, then Content-Language.

Author: PMAC
===============================================================================
"""
import asyncio

import pytest

from utils.heal_locale import by_language, page_language, subtag, track_language

EN, FR = "en-locator", "fr-locator"
BRANCHES = {"en": EN, "fr": FR}


class SyncPage:
    def __init__(self, html_lang="", locale="en-US"):
        self.signals, self.asked = [html_lang, locale], 0

    def evaluate(self, script):
        self.asked += 1
        return self.signals


class AsyncPage:
    """An async Playwright page: evaluate is a coroutine function, so a sync helper must not call it."""

    def __init__(self):
        self.handlers, self.signals, self.asked = {}, ["fr-CA", "en-US"], 0

    async def evaluate(self, script):
        self.asked += 1
        return self.signals

    def on(self, event, handler):
        self.handlers[event] = handler


class TestByLanguage:
    def test_returns_the_branch_of_the_page_language(self):
        assert by_language(SyncPage("fr-CA"), BRANCHES) == FR
        assert by_language(SyncPage("en"), BRANCHES) == EN

    def test_another_language_gets_the_first_entry_the_original_copy(self):
        assert by_language(SyncPage("de"), BRANCHES) == EN
        assert by_language(SyncPage("de"), {"fr": FR, "en": EN}) == FR

    def test_html_lang_wins_then_browser_locale(self):
        assert by_language(SyncPage("fr", "en-US"), BRANCHES) == FR
        assert by_language(SyncPage("", "fr-FR"), BRANCHES) == FR

    def test_an_async_page_is_never_asked_and_uses_the_recorded_language(self):
        page = AsyncPage()
        assert by_language(page, BRANCHES) == EN and page.asked == 0
        page._heal_language = "fr"
        assert by_language(page, BRANCHES) == FR and page.asked == 0

    def test_a_page_that_raises_gets_the_first_entry(self):
        class Broken:
            def evaluate(self, script):
                raise RuntimeError("closed")
        assert by_language(Broken(), BRANCHES) == EN
        assert by_language(object(), BRANCHES) == EN

    def test_no_branches_is_an_error(self):
        with pytest.raises(ValueError):
            by_language(SyncPage("en"), {})


class TestSignals:
    @pytest.mark.parametrize("value,expected", [("fr-CA", "fr"), ("EN_us", "en"), ("fr,en;q=0.8", "fr"), ("", ""),
                                                ("x", ""), ("english", ""), (None, ""), ("zh-Hans", "zh")])
    def test_subtag(self, value, expected):
        assert subtag(value) == expected

    def test_priority_html_lang_then_locale_then_content_language(self):
        assert page_language("fr", "en") == "fr"
        assert page_language("", "en-GB") == "en"
        assert page_language(None, None) == ""            # Content-Language is not a signal
        assert page_language("", "") == ""


class TestTrackLanguage:
    def test_the_async_page_language_is_recorded_on_domcontentloaded(self):
        page = AsyncPage()
        track_language(page)
        assert set(page.handlers) == {"domcontentloaded"}
        asyncio.run(page.handlers["domcontentloaded"]())
        assert page._heal_language == "fr" and by_language(page, BRANCHES) == FR

    def test_a_failing_evaluate_leaves_the_language_unset(self):
        page = AsyncPage()

        async def boom(script):
            raise RuntimeError("navigating")
        page.evaluate = boom
        track_language(page)
        asyncio.run(page.handlers["domcontentloaded"]())
        assert not hasattr(page, "_heal_language")

    def test_a_page_without_events_is_left_alone(self):
        track_language(object())
