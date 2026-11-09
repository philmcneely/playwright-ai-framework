"""
===============================================================================
Unit Tests: the heal client carries every key the probe lists and the service reads
===============================================================================
The probe lists row_attr, pw_text, pw_cut, top_at_center, copy_only, copy_cut and for_attr per element and copy_more for the
page; the allowlist keeps them (booleans only as booleans), the request carries `inventory_copy_more`, and the probe the client
vendors is the probe the service serves (a served probe whose bytes differ is refused).

Author: PMAC
===============================================================================
"""
import asyncio
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from utils import heal_advise as ha
from utils import heal_client as hc
from utils import heal_fingerprints as fp
from utils.heal_client import HealSettings
from utils.heal_redact import INVENTORY_KEYS, clean_inventory

BASE = "http://localhost:7080"
BOOLS = ("pw_cut", "top_at_center", "copy_only", "copy_cut", "copy_wrap", "disabled", "hidden")
STRINGS = ("row_attr", "pw_text", "for_attr", "row", "text")


def test_the_new_keys_are_on_the_allowlist():
    for key in ("row_attr", "pw_text", "pw_cut", "top_at_center", "copy_only", "copy_cut", "copy_wrap", "for_attr"):
        assert key in INVENTORY_KEYS, key


def test_the_new_keys_survive_with_their_types():
    item = {"tag": "span", "text": "Pending", "row": "order-1042", "row_attr": "data-qa", "pw_text": "Pending", "pw_cut": False,
            "top_at_center": True, "copy_only": True, "copy_cut": False, "for_attr": "email"}
    assert clean_inventory([item]) == [item]


@pytest.mark.parametrize("key", BOOLS)
@pytest.mark.parametrize("wrong", ["true", "", 1, 0, None, ["x"], {"a": 1}])
def test_a_boolean_key_with_another_type_is_dropped(key, wrong):
    assert clean_inventory([{"tag": "a", key: wrong}]) == [{"tag": "a"}]


@pytest.mark.parametrize("key", STRINGS)
@pytest.mark.parametrize("wrong", [True, False, 3, None, ["x"], {"a": 1}])
def test_a_string_key_with_another_type_is_dropped(key, wrong):
    assert clean_inventory([{"tag": "a", key: wrong}]) == [{"tag": "a"}]


def test_a_long_string_is_capped_like_the_other_fields():
    out = clean_inventory([{"tag": "a", "pw_text": "x" * 900, "for_attr": "y" * 900}])[0]
    assert len(out["pw_text"]) == 400 and len(out["for_attr"]) == 400


def test_a_key_that_reads_like_a_value_is_still_dropped():
    assert clean_inventory([{"tag": "a", "pw_text": "ok", "pw_value": "hunter2", "for_attr_token": "t"}]) == \
        [{"tag": "a", "pw_text": "ok"}]


def _page(**extra):
    return {"path": "/", "language": {}, "inventory": [], "more": 0, "viewport": {}, "aria": None, **extra}


def _request(page, tmp_path):
    return hc.build_request({"name": "t", "classname": "", "error": "x"}, [], [], page, HealSettings(), tmp_path)


def test_the_request_carries_inventory_copy_more(tmp_path):
    assert _request(_page(copy_more=7), tmp_path)["page"]["inventory_copy_more"] == 7


def test_a_page_without_copy_more_sends_zero(tmp_path):
    assert _request(_page(), tmp_path)["page"]["inventory_copy_more"] == 0


def test_the_request_carries_the_new_item_keys(tmp_path):
    item = {"ref": "e0", "tag": "span", "text": "Pending", "pw_text": "Pending", "pw_cut": False, "top_at_center": True,
            "copy_only": True, "copy_cut": True, "for_attr": "email", "row_attr": "data-qa", "row": "r1"}
    req = _request(_page(inventory=[item]), tmp_path)
    assert req["page"]["inventory"] == [item]


class _Page:
    url = BASE + "/"

    def __init__(self, data):
        self.data = data

    def evaluate(self, script):
        return self.data

    def locator(self, sel):
        return SimpleNamespace(aria_snapshot=lambda: "")

    frames = []


class _AsyncPage(_Page):
    async def evaluate(self, script):
        return self.data

    def locator(self, sel):
        async def aria():
            return ""
        return SimpleNamespace(aria_snapshot=aria)


def _live(data):
    live = hc.LivePage.__new__(hc.LivePage)
    live.page, live.probe = _Page(data), "probe"
    live.guard = SimpleNamespace(active=lambda: __import__("contextlib").nullcontext())
    return live


@pytest.mark.parametrize("raw,want", [(5, 5), (0, 0), (None, 0), ("x", 0), (-3, 0), (True, 0), (2.5, 0), (10**12, 1_000_000)])
def test_the_live_page_forwards_copy_more_as_a_capped_count(raw, want):
    data = {"page": {}, "items": [], "more": 0, "copy_more": raw}
    assert _live(data).snapshot()["copy_more"] == want
    assert asyncio.run(ha.snapshot_page(_AsyncPage(data)))["copy_more"] == want


def test_the_live_page_keeps_more_as_it_was():
    assert _live({"page": {}, "items": [], "more": 4}).snapshot()["more"] == 4


def test_copy_only_text_travels_like_any_other_text(tmp_path):
    items = [{"tag": "span", "text": "Total due", "copy_only": True, "copy_cut": True, "pw_text": "Total due", "pw_cut": False}]
    data = {"page": {}, "items": items, "more": 0, "copy_more": 3}
    snap = _live(data).snapshot()
    assert snap["inventory"][0]["copy_only"] is True and snap["inventory"][0]["pw_text"] == "Total due"
    assert _request(snap, tmp_path)["page"]["inventory_copy_more"] == 3


def test_a_fingerprint_keeps_the_keys_it_stored_before():
    item = {"tag": "span", "text": "Pending", "row": "r1", "row_attr": "data-qa", "pw_text": "Pending", "copy_only": True,
            "testid": "status"}
    out = fp.item_to_fingerprint(item)
    assert out["text"] == "Pending" and out["row"] == "r1" and out["attrs"]["data-testid"] == "status"
    assert not {"pw_text", "copy_only", "row_attr"} & set(out)


# ---- the vendored probe is the probe the service serves -------------------------------------------------------------------
def _service_probe():
    env = os.environ.get("HEAL_SERVICE_PROBE")
    if env and Path(env).is_file():
        return Path(env)
    try:
        import heal_service
    except ImportError:
        return None
    path = Path(heal_service.__file__).parent / "probe" / "probe.js"
    return path if path.is_file() else None


def test_the_vendored_probe_is_byte_identical_to_the_service_probe():
    served = _service_probe()
    if served is None:
        pytest.skip("heal_service is not importable here")
    ours, theirs = hc.PROBE_FILE.read_bytes(), served.read_bytes()
    assert hashlib.sha256(ours).hexdigest() == hashlib.sha256(theirs).hexdigest()


def test_the_vendored_probe_lists_the_keys_the_client_allows():
    text = hc.PROBE_FILE.read_text(encoding="utf-8")
    for key in ("copy_more", "copy_only", "copy_cut", "for_attr", "pw_text", "pw_cut", "top_at_center", "row_attr"):
        assert key in text, key
