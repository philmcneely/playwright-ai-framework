"""
===============================================================================
Language Branch Helper (by_language) for Healed Copy-Based Locators
===============================================================================
A locator built from page copy (role + name, label, placeholder, text) only works in the language the copy is written in.
When the heal service sees that the page now renders in another language than the passing run, it keeps both: it writes
code that picks a locator by the page's language, and that code calls the helper in this module:

    by_language(self.page, {"en": self.page.get_by_label('Username'), "fr": self.page.get_by_label("Nom d'utilisateur")})

The helper returns the entry for the page's language, and the FIRST entry (the original copy) for any other language, so
a run in a language nobody healed for behaves exactly as it did before the heal. Copy is never translated.

The page language is read from <html lang>, then the browser locale, never from words on the page (the Content-Language header
is not used: the helper cannot see it in the test run, and the heal client picks branches by the same two signals). A sync
Playwright page is asked directly. An async page cannot be asked from this sync function, so its language is the
one `track_language(page)` last recorded (call it once when the page is created; the framework's `page` fixture does).

Difference from the TypeScript framework: on a page with NO <html lang> this helper (and the Python heal client, which uses the
same two signals) falls back to the browser locale (`navigator.language`), while the TypeScript helper reads only the CSS
`html:lang()` match and so keeps the first entry. Each side is consistent with itself (the branch the client checked live is the
branch the helper picks at run time), but the two languages do not make the same choice on such a page: give the page an
<html lang> if you rely on the same behaviour in both.

Features:
    ✓ by_language(receiver, branches): the locator of the page's language, else the first one
    ✓ page_language(html_lang, browser_locale): the plain language subtag from the two signals, in priority order
    ✓ track_language(page): keeps `page._heal_language` current on an async page (domcontentloaded)
    ✓ Never raises on a page that cannot be asked: the first entry is returned instead

Environment Variables:
    None.

Author: PMAC
===============================================================================
"""
import inspect
import re
from typing import Any, Dict, Optional

_SUBTAG = re.compile(r"^[A-Za-z]{2,3}$")
_SIGNALS_JS = "() => [document.documentElement.lang || '', navigator.language || '']"
ATTR = "_heal_language"


def subtag(value: Optional[str]) -> str:
    """The plain primary language subtag of `value` ("fr-CA" -> "fr"), lower case; "" when it is not one."""
    first = (value or "").strip().replace("_", "-").split("-", 1)[0].split(",", 1)[0].split(";", 1)[0].strip()
    return first.lower() if _SUBTAG.match(first) else ""


def page_language(html_lang: Optional[str] = None, browser_locale: Optional[str] = None) -> str:
    """The language subtag from <html lang>, then the browser locale ("" when neither is usable)."""
    for value in (html_lang, browser_locale):
        found = subtag(value)
        if found:
            return found
    return ""


def _current_language(receiver: Any) -> str:
    """The receiver's language: the recorded one, else (sync page only) a fresh read of the page."""
    recorded = getattr(receiver, ATTR, None)
    if isinstance(recorded, str) and recorded:
        return recorded
    evaluate = getattr(receiver, "evaluate", None)
    if evaluate is None or inspect.iscoroutinefunction(evaluate):
        return ""
    try:
        html_lang, locale = evaluate(_SIGNALS_JS)
    except Exception:
        return ""
    return page_language(html_lang, locale)


def by_language(receiver: Any, branches: Dict[str, Any]) -> Any:
    """The entry of `branches` for the page's language, else the first entry (the original copy)."""
    if not branches:
        raise ValueError("by_language needs at least one branch")
    wanted = _current_language(receiver)
    if wanted and wanted in branches:
        return branches[wanted]
    return next(iter(branches.values()))


def track_language(page: Any) -> None:
    """Keep `page._heal_language` current on an async Playwright page. Safe to call on any page; failures are ignored."""
    async def refresh(*_: Any) -> None:
        try:
            html_lang, locale = await page.evaluate(_SIGNALS_JS)
            setattr(page, ATTR, page_language(html_lang, locale))
        except Exception:
            pass                                 # a page that is closing or navigating: the next load refreshes it

    try:
        page.on("domcontentloaded", refresh)
    except Exception:
        pass


__all__ = ["by_language", "page_language", "subtag", "track_language"]
