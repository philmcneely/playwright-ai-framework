"""
===============================================================================
Unit Tests: utils/ai_healing.py — _parse_ollama_response
===============================================================================
Exercises every fallback strategy of the Ollama response parser with the kinds
of malformed output small local models actually produce. No Ollama service is
contacted — the parser is pure string handling.

Author: PMAC
===============================================================================
"""

import pytest

from utils.ai_healing import OllamaAIHealingService, strip_style_tags


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setenv("AI_HEALING_ENABLED", "false")
    return OllamaAIHealingService()


class TestParseOllamaResponse:
    def test_none_response_returns_none(self, service):
        assert service._parse_ollama_response(None) is None

    def test_empty_response_returns_none(self, service):
        assert service._parse_ollama_response("") is None

    def test_strategy1_json_code_block(self, service):
        response = (
            "Here is my analysis:\n```json\n"
            '{"analysis": "selector changed", "confidence": 0.9}\n'
            "```\nHope that helps!"
        )
        parsed = service._parse_ollama_response(response)
        assert parsed == {"analysis": "selector changed", "confidence": 0.9}

    def test_strategy2_generic_code_block(self, service):
        response = '```\n{"analysis": "timing issue", "confidence": 0.8}\n```'
        parsed = service._parse_ollama_response(response)
        assert parsed == {"analysis": "timing issue", "confidence": 0.8}

    def test_strategy3_json_embedded_in_prose(self, service):
        response = (
            "Sure! Based on the failure I think: "
            '{"analysis": "element hidden", "confidence": 0.7} '
            "Let me know if you need more."
        )
        parsed = service._parse_ollama_response(response)
        assert parsed == {"analysis": "element hidden", "confidence": 0.7}

    def test_strategy4_bare_json_response(self, service):
        response = '{"analysis": "flaky network", "root_cause": "slow API"}'
        parsed = service._parse_ollama_response(response)
        assert parsed == {"analysis": "flaky network", "root_cause": "slow API"}

    def test_strategy5_cleans_junk_around_json_in_code_block(self, service):
        response = '```\nSure thing! {"analysis": "ok"} -- done\n```'
        parsed = service._parse_ollama_response(response)
        assert parsed == {"analysis": "ok"}

    def test_strategy6_manual_field_extraction(self, service):
        response = (
            'Unstructured output. "analysis": "Selector renamed", '
            '"root_cause": "DOM refactor", "confidence": 0.75 -- end'
        )
        parsed = service._parse_ollama_response(response)
        assert parsed["analysis"] == "Selector renamed"
        assert parsed["root_cause"] == "DOM refactor"
        assert parsed["confidence"] == 0.75
        assert "Manual review required" in parsed["suggested_fix"]

    def test_manual_extraction_defaults_for_plain_text(self, service):
        response = "complete nonsense with no json structure at all"
        parsed = service._parse_ollama_response(response)
        assert parsed["analysis"] == response
        assert parsed["root_cause"] == "Could not extract root cause"
        assert parsed["confidence"] == 0.3

    def test_final_fallback_returns_raw_response(self, service):
        # An invalid confidence value forces the manual-extraction strategy to
        # raise, exercising the structured raw-response fallback.
        response = 'garbled "confidence": 1.2.3 output'
        parsed = service._parse_ollama_response(response)
        assert parsed["confidence"] == 0.2
        assert parsed["raw_unparsed_response"] == response
        assert parsed["root_cause"] == "Could not parse structured response"


class TestStripStyleTags:
    def test_removes_style_blocks(self):
        html = "<html><style>body { color: red; }</style><body>hi</body></html>"
        assert strip_style_tags(html) == "<html><body>hi</body></html>"

    def test_removes_multiline_and_multiple_blocks(self):
        html = "<style>\na { x: 1; }\n</style>text<STYLE>b {}</STYLE>more"
        assert strip_style_tags(html) == "textmore"

    def test_html_without_style_unchanged(self):
        html = "<div>no styles here</div>"
        assert strip_style_tags(html) == html
