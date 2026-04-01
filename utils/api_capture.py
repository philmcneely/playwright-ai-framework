"""Capture API requests/responses during test execution for debugging."""
import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CapturedRequest:
    method: str
    url: str
    status: int = 0
    request_headers: dict = field(default_factory=dict)
    response_headers: dict = field(default_factory=dict)
    response_body: str = ""
    duration_ms: float = 0
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "url": self.url,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "request_headers": self.request_headers,
            "response_headers": self.response_headers,
            "response_body": self.response_body[:10240] if self.response_body else "",
        }


class APICapture:
    """Captures API requests/responses during Playwright test execution."""

    # Skip static assets
    SKIP_EXTENSIONS = {".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ttf", ".ico"}

    def __init__(self):
        self.requests: list[CapturedRequest] = []
        self._pending: dict[str, CapturedRequest] = {}

    def _should_capture(self, url: str) -> bool:
        """Only capture API calls, skip static assets."""
        from urllib.parse import urlparse
        path = urlparse(url).path.lower()
        return not any(path.endswith(ext) for ext in self.SKIP_EXTENSIONS)

    def on_request(self, request) -> None:
        """Playwright request event handler."""
        if not self._should_capture(request.url):
            return
        captured = CapturedRequest(
            method=request.method,
            url=request.url,
            request_headers=dict(request.headers) if request.headers else {},
            timestamp=datetime.now().isoformat(),
        )
        self._pending[request.url] = captured

    def on_response(self, response) -> None:
        """Playwright response event handler."""
        if response.url not in self._pending:
            return
        captured = self._pending.pop(response.url)
        captured.status = response.status
        captured.response_headers = dict(response.headers) if response.headers else {}
        try:
            body = response.body()
            if isinstance(body, bytes):
                body = body.decode("utf-8", errors="replace")
            captured.response_body = body[:10240]  # cap at 10KB
        except Exception:
            captured.response_body = "<could not read body>"
        self.requests.append(captured)

    def to_json(self) -> str:
        """Serialize all captured requests to JSON."""
        return json.dumps([r.to_dict() for r in self.requests], indent=2)

    def summary(self) -> str:
        """One-line-per-request summary for reports."""
        lines = []
        for r in self.requests:
            lines.append(f"{r.method} {r.status} {r.url} ({r.duration_ms:.0f}ms)")
        return "\n".join(lines)

    def clear(self):
        self.requests.clear()
        self._pending.clear()
