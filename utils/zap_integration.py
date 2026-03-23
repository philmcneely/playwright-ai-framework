"""OWASP ZAP passive scanning integration for Playwright tests."""
import json
import os
import time
from typing import Optional


class ZAPIntegration:
    """Manages ZAP proxy connection and alert retrieval."""

    def __init__(
        self,
        proxy_host: str = "localhost",
        proxy_port: int = 8080,
        api_key: str = "",
    ):
        self.proxy_host = proxy_host
        self.proxy_port = int(proxy_port)
        self.api_key = api_key or os.getenv("ZAP_API_KEY", "")
        self.base_url = f"http://{self.proxy_host}:{self.proxy_port}"
        self.enabled = os.getenv("ZAP_ENABLED", "false").lower() == "true"

    @property
    def proxy_url(self) -> str:
        return f"http://{self.proxy_host}:{self.proxy_port}"

    def is_running(self) -> bool:
        """Check if ZAP is accessible."""
        if not self.enabled:
            return False
        try:
            import requests
            resp = requests.get(
                f"{self.base_url}/JSON/core/view/version/",
                params={"apikey": self.api_key},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def get_alerts(self, min_risk: str = "Low") -> list[dict]:
        """Retrieve alerts from ZAP after test run.

        Args:
            min_risk: Minimum risk level to include (Informational, Low, Medium, High)
        """
        if not self.enabled:
            return []
        try:
            import requests
            risk_levels = {"Informational": 0, "Low": 1, "Medium": 2, "High": 3}
            min_level = risk_levels.get(min_risk, 1)

            resp = requests.get(
                f"{self.base_url}/JSON/core/view/alerts/",
                params={"apikey": self.api_key, "start": "0", "count": "100"},
                timeout=10,
            )
            if resp.status_code != 200:
                return []

            all_alerts = resp.json().get("alerts", [])
            filtered = [
                a for a in all_alerts
                if risk_levels.get(a.get("risk", "Informational"), 0) >= min_level
            ]
            return filtered
        except Exception as e:
            print(f"ZAP alert retrieval failed: {e}")
            return []

    def get_alerts_summary(self) -> dict:
        """Get summary of alerts by risk level."""
        alerts = self.get_alerts(min_risk="Informational")
        summary = {"High": 0, "Medium": 0, "Low": 0, "Informational": 0}
        for alert in alerts:
            risk = alert.get("risk", "Informational")
            summary[risk] = summary.get(risk, 0) + 1
        return summary

    def generate_report(self) -> str:
        """Generate a markdown report of ZAP findings."""
        alerts = self.get_alerts()
        if not alerts:
            return "# ZAP Security Scan\n\nNo security alerts found."

        lines = ["# ZAP Passive Scan Report", ""]
        summary = self.get_alerts_summary()
        lines.append(f"**High:** {summary['High']} | **Medium:** {summary['Medium']} | **Low:** {summary['Low']}")
        lines.append("")

        for alert in sorted(alerts, key=lambda a: {"High": 0, "Medium": 1, "Low": 2}.get(a.get("risk", ""), 3)):
            lines.append(f"## [{alert.get('risk', '?')}] {alert.get('alert', 'Unknown')}")
            lines.append(f"- **URL:** {alert.get('url', 'N/A')}")
            lines.append(f"- **Description:** {alert.get('description', 'N/A')[:200]}")
            lines.append(f"- **Solution:** {alert.get('solution', 'N/A')[:200]}")
            lines.append("")

        return "\n".join(lines)

    def get_browser_proxy_config(self) -> dict:
        """Return proxy config dict for Playwright browser launch."""
        if not self.enabled:
            return {}
        return {"proxy": {"server": self.proxy_url}}
