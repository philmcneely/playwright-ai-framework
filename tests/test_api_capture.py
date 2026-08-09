"""Tests for API capture utility."""
import pytest
from utils.api_capture import APICapture, CapturedRequest


def test_should_capture_api_calls():
    cap = APICapture()
    assert cap._should_capture("https://api.example.com/users") is True
    assert cap._should_capture("https://cdn.example.com/style.css") is False
    assert cap._should_capture("https://cdn.example.com/logo.png") is False
    assert cap._should_capture("https://api.example.com/data.json") is True


def test_captured_request_to_dict():
    req = CapturedRequest(method="GET", url="https://api.test.com/v1/users", status=200)
    d = req.to_dict()
    assert d["method"] == "GET"
    assert d["status"] == 200
    assert d["url"] == "https://api.test.com/v1/users"


def test_response_body_truncation():
    req = CapturedRequest(method="POST", url="https://api.test.com", response_body="x" * 20000)
    d = req.to_dict()
    assert len(d["response_body"]) == 10240


def test_summary_output():
    cap = APICapture()
    cap.requests = [
        CapturedRequest(method="GET", url="https://api.test.com/users", status=200, duration_ms=45),
        CapturedRequest(method="POST", url="https://api.test.com/login", status=401, duration_ms=120),
    ]
    summary = cap.summary()
    assert "GET 200" in summary
    assert "POST 401" in summary


def test_to_json():
    cap = APICapture()
    cap.requests = [CapturedRequest(method="GET", url="https://test.com", status=200)]
    j = cap.to_json()
    assert '"method": "GET"' in j


def test_clear():
    cap = APICapture()
    cap.requests = [CapturedRequest(method="GET", url="https://test.com", status=200)]
    cap.clear()
    assert len(cap.requests) == 0
