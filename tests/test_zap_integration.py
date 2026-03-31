"""Tests for ZAP integration utility."""
import pytest
from utils.zap_integration import ZAPIntegration


def test_proxy_url():
    zap = ZAPIntegration(proxy_host="localhost", proxy_port=8080)
    assert zap.proxy_url == "http://localhost:8080"


def test_disabled_by_default():
    zap = ZAPIntegration()
    assert not zap.enabled
    assert not zap.is_running()
    assert zap.get_alerts() == []
    assert zap.get_browser_proxy_config() == {}


def test_proxy_config_when_enabled(monkeypatch):
    monkeypatch.setenv("ZAP_ENABLED", "true")
    zap = ZAPIntegration()
    assert zap.enabled
    config = zap.get_browser_proxy_config()
    assert "proxy" in config
    assert config["proxy"]["server"] == "http://localhost:8080"


def test_custom_port():
    zap = ZAPIntegration(proxy_port=9090)
    assert zap.proxy_url == "http://localhost:9090"
    assert zap.proxy_port == 9090


def test_generate_report_no_alerts():
    zap = ZAPIntegration()
    report = zap.generate_report()
    assert "No security alerts" in report


def test_alerts_summary():
    zap = ZAPIntegration()
    summary = zap.get_alerts_summary()
    assert summary == {"High": 0, "Medium": 0, "Low": 0, "Informational": 0}
