"""
===============================================================================
Unit Tests: the heal client's vision option (HEAL_VISION, HEAL_MASK)
===============================================================================
What the client sends and, more to the point, what it never sends. With vision off the page is never asked for a screenshot
and no image byte is in the request; with auto or on exactly one viewport screenshot is taken, with password inputs and the
HEAL_MASK locators masked, never full page, and a capture that cannot be masked is not sent at all. A real Chromium checks
that the mask is really painted over a password field (skipped when no browser build is installed).

Author: PMAC
===============================================================================
"""
import base64
import io
import json
import struct
import zlib
from contextlib import contextmanager

import pytest

from tests.unit.test_heal_client import FAILURE, FakeLive, FakeService, Verify, healer, project, reply  # noqa: F401
from utils.heal_client import HealSettings, LivePage, build_request, png_screenshot, vision_mode


def png(width=40, height=30):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    rows = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


class LiveWithShot(FakeLive):
    """A fake page that can take a screenshot, and remembers whether it was asked."""

    def __init__(self, data=None, scroll=None, **kw):
        super().__init__(**kw)
        self.data, self.scroll, self.shots = data if data is not None else png(), scroll, 0

    def snapshot(self):
        snap = super().snapshot()
        return {**snap, "scroll": self.scroll or {"x": 0, "y": 0}}

    def screenshot(self):
        self.shots += 1
        return png_screenshot(self.data)


class NeverAsked(FakeLive):
    """A fake page whose screenshot must not be called: asking for one fails the test."""

    def screenshot(self):
        raise AssertionError("a screenshot was requested with HEAL_VISION off")


def run(project, vision, live, mask=None):
    svc = FakeService(reply("not_drift"))
    h = healer(project, svc, Verify(), live)
    h.settings = HealSettings(url="http://svc", vision=vision, mask=mask or [])
    h.heal(FAILURE)
    return svc.posts("/v1/heal")[0], svc


# ---- off: zero image bytes -------------------------------------------------------------------------------------------
class TestOff:
    @pytest.mark.parametrize("value", ["off", "", "OFF", "yes", "true", "1", "maybe", "full"])
    def test_anything_but_auto_or_on_never_asks_the_page_for_a_screenshot_and_sends_none(self, project, value):
        body, svc = run(project, value.lower() or "off", NeverAsked())
        assert body["page"]["screenshot"] is None and body["options"]["vision"] == "off"
        assert "scroll" not in body["page"]["viewport"]
        wire = json.dumps(svc.requests, default=str)
        assert "image/png" not in wire and "iVBOR" not in wire and "base64" not in wire.lower()

    def test_the_default_setting_is_off(self):
        assert HealSettings().vision == "off" and HealSettings.from_env({}).vision == "off"
        assert vision_mode(HealSettings(vision="Auto")) == "off"        # only the lower-case words count after from_env


# ---- auto and on: one masked viewport shot ----------------------------------------------------------------------------
class TestOn:
    @pytest.mark.parametrize("mode", ["auto", "on"])
    def test_one_screenshot_in_the_wire_format_with_the_mode_and_the_scroll(self, project, mode):
        live = LiveWithShot(png(64, 48), scroll={"x": 0, "y": 600})
        body, svc = run(project, mode, live)
        shot = body["page"]["screenshot"]
        assert live.shots == 1 and body["options"]["vision"] == mode
        assert set(shot) == {"media_type", "data", "width", "height"} and shot["media_type"] == "image/png"
        assert (shot["width"], shot["height"]) == (64, 48) and base64.b64decode(shot["data"]) == png(64, 48)
        assert body["page"]["viewport"] == {"w": 1280, "h": 720, "dpr": 1, "scroll": {"x": 0, "y": 600}}

    def test_no_screenshot_taken_means_vision_is_reported_off(self, project):
        live = LiveWithShot(data=b"not a png")
        body, _ = run(project, "auto", live)
        assert body["page"]["screenshot"] is None and body["options"]["vision"] == "off"

    def test_a_page_that_cannot_screenshot_does_not_stop_the_heal(self, project):
        body, _ = run(project, "auto", FakeLive())               # no screenshot method at all
        assert body["page"]["screenshot"] is None and body["options"]["vision"] == "off"

    def test_the_screenshot_is_in_the_request_once_and_nowhere_else(self, project):
        body, svc = run(project, "on", LiveWithShot())
        assert json.dumps(svc.requests, default=str).count(body["page"]["screenshot"]["data"][:80]) == 1


class TestWireForm:
    def test_png_screenshot_reads_the_size_from_the_png(self):
        assert png_screenshot(png(7, 9))["width"] == 7 and png_screenshot(png(7, 9))["height"] == 9

    @pytest.mark.parametrize("data", [None, "text", b"", b"\xff\xd8\xff" + b"\x00" * 40, b"GIF89a" + b"\x00" * 40,
                                      b"\x89PNG\r\n\x1a\n" + b"\x00" * 40])
    def test_what_is_not_a_png_is_not_sent(self, data):
        assert png_screenshot(data) is None

    def test_the_services_limits_are_kept_on_this_side_too(self):
        assert png_screenshot(png() + b"\x00" * (4 * 1024 * 1024)) is None
        header = png()
        huge = header[:16] + struct.pack(">II", 9000, 10) + header[24:]
        assert png_screenshot(huge) is None

    def test_build_request_ignores_a_screenshot_when_vision_is_off(self, project):
        page = {"path": "/", "language": {}, "inventory": [], "more": 0, "viewport": {"w": 1, "h": 1, "dpr": 1}, "aria": "",
                "scroll": {"x": 5, "y": 6}, "screenshot": png_screenshot(png())}
        req = build_request({"name": "t", "error": "e"}, [], [], page, HealSettings(vision="off"), project)
        assert req["page"]["screenshot"] is None and req["options"]["vision"] == "off" and "scroll" not in req["page"]["viewport"]
        req = build_request({"name": "t", "error": "e"}, [], [], page, HealSettings(vision="auto"), project)
        assert req["page"]["screenshot"]["media_type"] == "image/png" and req["page"]["viewport"]["scroll"] == {"x": 5, "y": 6}


# ---- the capture itself, with a fake Playwright page --------------------------------------------------------------------
class FakeLocator:
    def __init__(self, owner, selector):
        self.owner, self.selector = owner, selector


class FakeFrame:
    def __init__(self, name):
        self.name = name

    def locator(self, selector):
        return FakeLocator(self.name, selector)


class FakePage(FakeFrame):
    url = "http://localhost:7080/login"

    def __init__(self, fail=None):
        super().__init__("main")
        self.main_frame = self
        self.frames = [self, FakeFrame("child-1"), FakeFrame("child-2")]
        self.calls, self.fail = [], fail

    def screenshot(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise self.fail
        return png(20, 10)


def live_page(vision="auto", mask=None, page=None):
    lp = LivePage(HealSettings(vision=vision, mask=mask or []), "/", "probe")
    lp.page = page or FakePage()
    return lp


class TestCapture:
    def test_one_viewport_shot_masking_every_password_input_and_every_heal_mask_locator(self):
        lp = live_page(mask=["#card-number", ".ssn, .dob"])
        assert lp.screenshot()["media_type"] == "image/png"
        (kw,) = lp.page.calls
        assert "full_page" not in kw and kw["type"] == "png" and kw["mask_color"] == "#000000"
        assert kw["animations"] == "disabled" and kw["caret"] == "hide"
        picked = [(m.owner, m.selector) for m in kw["mask"]]
        assert ("main", "input[type=password]") in picked and ("child-1", "input[type=password]") in picked
        assert ("child-2", "input[type=password]") in picked
        assert ("main", "#card-number") in picked and ("main", ".ssn, .dob") in picked

    def test_off_never_calls_playwright(self):
        lp = live_page(vision="off")
        assert lp.screenshot() is None and lp.page.calls == []

    def test_a_failure_while_capturing_sends_nothing_and_never_retries_unmasked(self):
        lp = live_page(page=FakePage(fail=RuntimeError("selector did not resolve")))
        assert lp.screenshot() is None and len(lp.page.calls) == 1 and all("mask" in c for c in lp.page.calls)

    def test_a_mask_that_cannot_be_built_sends_nothing(self):
        page = FakePage()

        def boom(selector):
            raise ValueError("bad selector")
        page.locator = boom
        lp = live_page(mask=["###"], page=page)
        assert lp.screenshot() is None and page.calls == []


# ---- a real browser: the mask is really painted ------------------------------------------------------------------------
def _browser():
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        b = p.chromium.launch()
        return p, b
    except Exception:
        return None, None


PAGE = """<!doctype html><html><body style="margin:0;background:#fff">
<input id="pw" type="password" style="position:absolute;left:20px;top:20px;width:200px;height:40px;background:#ff0000;border:0">
<input id="card" type="text" style="position:absolute;left:20px;top:100px;width:200px;height:40px;background:#00ff00;border:0">
<input id="plain" type="text" style="position:absolute;left:20px;top:180px;width:200px;height:40px;background:#0000ff;border:0">
<div style="height:3000px"></div></body></html>"""


def pixel(data, x, y):
    from PIL import Image
    return Image.open(io.BytesIO(data)).convert("RGB").getpixel((x, y))


def test_a_real_screenshot_has_the_password_field_and_the_mask_locator_blacked_out_and_is_viewport_only():
    pytest.importorskip("PIL", reason="Pillow is not installed")
    p, b = _browser()
    if b is None:
        pytest.skip("no Playwright Chromium build is installed")
    try:
        page = b.new_page(viewport={"width": 400, "height": 300})
        page.set_content(PAGE)
        lp = LivePage(HealSettings(vision="auto", mask=["#card"]), "/", "probe")
        lp.page = page
        shot = lp.screenshot()
        data = base64.b64decode(shot["data"])
        assert (shot["width"], shot["height"]) == (400, 300)                    # the viewport, not the 3000 px page
        assert pixel(data, 100, 40) == (0, 0, 0)                                 # the password input
        assert pixel(data, 100, 120) == (0, 0, 0)                                # the HEAL_MASK locator
        assert pixel(data, 100, 200) == (0, 0, 255)                              # an ordinary field is left as it is
        page.evaluate("window.scrollTo(0, 50)")
        again = lp.screenshot()
        assert (again["width"], again["height"]) == (400, 300)
    finally:
        b.close()
        p.stop()
