"""
Jira Integration Client for Playwright Test Framework

Posts test results to Jira tickets and manages workflow transitions.
Conditionally enabled via JIRA_ENABLED environment variable.

Environment Variables:
    JIRA_ENABLED: Enable Jira reporting (true|false, default: false)
    JIRA_BASE: Jira instance URL
    JIRA_USER: Jira username/email
    JIRA_TOKEN: Jira API token
    JIRA_JQL: JQL query for ticket filtering
    JIRA_DRY_RUN: Log instead of posting (true|false, default: false)
    JIRA_TRANSITION_ON_PASS: Workflow transition name on test pass
    JIRA_TRANSITION_ON_FAIL: Workflow transition name on test fail
"""

import os
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests

from utils.debug import debug_print

logger = logging.getLogger(__name__)

TICKET_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


@dataclass
class JiraTestResult:
    ticket_id: str
    test_name: str
    status: str
    duration_ms: int
    error_message: Optional[str] = None
    test_file: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class JiraClient:
    def __init__(self):
        self.enabled = os.getenv("JIRA_ENABLED", "false").lower() == "true"
        self.base_url = os.getenv("JIRA_BASE", "")
        self.username = os.getenv("JIRA_USER", "")
        self.token = os.getenv("JIRA_TOKEN", "")
        self.jql = os.getenv(
            "JIRA_JQL", 'project = ABC AND status in ("To Do", "In Progress")'
        )
        self.dry_run = os.getenv("JIRA_DRY_RUN", "false").lower() == "true"
        self.transition_on_pass = os.getenv("JIRA_TRANSITION_ON_PASS")
        self.transition_on_fail = os.getenv("JIRA_TRANSITION_ON_FAIL")

    def _auth(self):
        return (self.username, self.token)

    def post_comment(self, ticket_id: str, body: str) -> bool:
        if self.dry_run:
            logger.info(f"[Jira DRY RUN] Would post to {ticket_id}: {body[:120]}...")
            return True

        url = f"{self.base_url}/rest/api/2/issue/{ticket_id}/comment"
        try:
            resp = requests.post(
                url,
                auth=self._auth(),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={"body": body},
                timeout=30,
            )
            if resp.status_code == 201:
                debug_print(f"[Jira] Comment posted to {ticket_id}")
                return True
            logger.error(
                f"[Jira] Failed to post to {ticket_id}: {resp.status_code} {resp.text}"
            )
            return False
        except requests.RequestException as e:
            logger.error(f"[Jira] Request failed for {ticket_id}: {e}")
            return False

    def transition_ticket(self, ticket_id: str, transition_name: str) -> bool:
        if self.dry_run:
            logger.info(
                f"[Jira DRY RUN] Would transition {ticket_id} to {transition_name}"
            )
            return True

        url = f"{self.base_url}/rest/api/2/issue/{ticket_id}/transitions"
        try:
            resp = requests.get(url, auth=self._auth(), timeout=30)
            if not resp.ok:
                logger.error(
                    f"[Jira] Failed to get transitions for {ticket_id}: {resp.text}"
                )
                return False

            transitions = resp.json().get("transitions", [])
            match = next(
                (
                    t
                    for t in transitions
                    if t["name"].lower() == transition_name.lower()
                ),
                None,
            )
            if not match:
                logger.error(
                    f"[Jira] Transition '{transition_name}' not found for {ticket_id}"
                )
                return False

            resp = requests.post(
                url,
                auth=self._auth(),
                headers={"Content-Type": "application/json"},
                json={"transition": {"id": match["id"]}},
                timeout=30,
            )
            if resp.status_code == 204:
                debug_print(f"[Jira] Transitioned {ticket_id} to {transition_name}")
                return True
            logger.error(f"[Jira] Failed to transition {ticket_id}: {resp.text}")
            return False
        except requests.RequestException as e:
            logger.error(f"[Jira] Transition failed for {ticket_id}: {e}")
            return False

    def format_result_comment(self, result: JiraTestResult) -> str:
        emoji = {"passed": "✅", "failed": "❌", "skipped": "⏭️", "error": "💥"}
        comment = f"{emoji.get(result.status, '❓')} *Automated Test Result*\n\n"
        comment += f"*Test:* {result.test_name}\n"
        comment += f"*Status:* {result.status.upper()}\n"
        comment += f"*Duration:* {result.duration_ms}ms\n"
        comment += f"*Timestamp:* {result.timestamp}\n"
        if result.test_file:
            comment += f"*Test File:* {{{{{result.test_file}}}}}\n"
        if result.error_message and result.status == "failed":
            truncated = result.error_message[:2000]
            comment += f"\n*Error Details:*\n{{code}}\n{truncated}\n{{code}}\n"
        comment += (
            "\n_This comment was automatically generated by playwright-ai-framework._"
        )
        return comment

    def report_test_result(self, result: JiraTestResult) -> bool:
        comment = self.format_result_comment(result)
        posted = self.post_comment(result.ticket_id, comment)

        if posted and result.status == "passed" and self.transition_on_pass:
            self.transition_ticket(result.ticket_id, self.transition_on_pass)
        if posted and result.status == "failed" and self.transition_on_fail:
            self.transition_ticket(result.ticket_id, self.transition_on_fail)

        return posted


_client: Optional[JiraClient] = None


def get_jira_client() -> JiraClient:
    global _client
    if _client is None:
        _client = JiraClient()
    return _client


def extract_ticket_id(nodeid: str) -> Optional[str]:
    match = TICKET_PATTERN.search(nodeid)
    return match.group(1) if match else None
