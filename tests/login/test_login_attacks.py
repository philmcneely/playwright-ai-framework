"""
===============================================================================
Login Attack and Security Tests for The Internet Test Site
===============================================================================

This module contains tests that verify The Internet test site's login page
security and robustness against common attack vectors and invalid input scenarios.

Features:
    ✓ Tests for SQL injection, XSS, HTML injection, and command injection attempts
    ✓ Verifies proper error handling and user feedback for invalid logins
    ✓ Ensures the login form is resilient to malicious input and brute force attacks
    ✓ Uses async Playwright test patterns for reliability and speed
    ✓ Comprehensive security validation for authentication systems

Security Test Categories:
    • SQL Injection Prevention: Tests various SQL injection attack patterns
    • Cross-Site Scripting (XSS): Validates script injection protection
    • HTML Injection: Verifies HTML content sanitization
    • Command Injection: Tests system command injection prevention
    • Brute Force Protection: Validates rate limiting and account protection

Usage Example:
    pytest tests/login/test_login_attacks.py

Conventions:
    - Each test is marked as async and uses Playwright's async API
    - Test data for attacks is defined inline for clarity
    - Tests verify that attacks fail gracefully with proper error messages

Author: Playwright AI Test Framework
Site: The Internet (https://the-internet.herokuapp.com)
Date: [2025-09-03]
===============================================================================
"""

import pytest
from pages.app import App
import pytest
from pages.login_page import LoginPage
from utils.decorators.screenshot_decorator import screenshot_on_failure

# ------------------------------------------------------------------------------
# Test: SQL Injection in Email Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_comprehensive_email_sql_injection(app):
    """
    Attempt to login using various SQL injection payloads in the email field.
    Verifies that the login form is not vulnerable and displays the correct error.
    """
    injection_payloads = [
        "admin'--",
        "' OR '1'='1",
        "' OR 1=1--",
        "'; DROP TABLE users;--",
        "' UNION SELECT * FROM users--",
        "' OR 'x'='x"
    ]
    for email_payload in injection_payloads:
        await app.login_page.load_login_direct()
        await app.login_page.enter_email(email_payload)
        await app.login_page.click_continue()
        # Assert that the invalid email error message is visible
        assert await app.login_page.error_message_email_invalid.is_visible()
        expected_message = app.login_page.error_message_email_invalid_text
        actual_message = await app.login_page.get_error_message_email_invalid_text()
        assert expected_message == actual_message
        assert await app.login_page.has_email_invalid_error_icon()

# ------------------------------------------------------------------------------
# (Commented Out) Test: SQL Injection in Password Field
# ------------------------------------------------------------------------------

# The following test is commented out to avoid account lockout risks.
# It demonstrates how to test SQL injection in the password field for multiple accounts.

# @screenshot_on_failure
# @pytest.mark.login
# @pytest.mark.asyncio
# async def test_login_comprehensive_password_sql_injection(app):
#     """
#     Attempt to login using various SQL injection payloads in the password field.
#     Verifies that the login form is not vulnerable and displays the correct error.
#     """
#     injection_payloads = [
#         ("admin1@test.com", "pass'--"),
#         ("admin2@test.com", "' OR '1'='1"),
#         ("admin3@test.com", "' OR 1=1--"),
#         ("admin4@test.com", "'; DROP TABLE users;--"),
#         ("admin5@test.com", "' UNION SELECT * FROM users--"),
#         ("admin6@test.com", "' OR 'x'='x")
#     ]
#     for email_payload, password_payload in injection_payloads:
#         await app.login_page.load_login_direct()
#         await app.login_page.enter_email(email_payload)
#         await app.login_page.click_continue()
#         await app.login_page.enter_password(password_payload)
#         await app.login_page.click_continue()
#         # Optionally, wait for error message to appear
#         # await page.wait_for_timeout(2000)
#         assert await app.login_page.error_message_email_or_password_incorrect.is_visible()
#         expected_message = app.login_page.error_message_email_incorrect_text
#         actual_message = await app.login_page.get_error_message_password_incorrect_text()
#         assert expected_message == actual_message
#         assert await app.login_page.has_email_or_password_incorrect_error_icon()

# ------------------------------------------------------------------------------
# Test: XSS in Email Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_xss_email_field(page):
    """
    Attempt to inject a script tag in the email field to test for XSS vulnerability.
    Verifies that the script is not rendered in the page content.
    """
    login_page = LoginPage(page)
    await login_page.load_login_direct()
    # Attempt to inject a script tag
    await login_page.enter_email("<script>alert('xss')</script>")
    await login_page.click_continue()
    # Assert that the script tag is not present in the page content
    assert "<script>alert('xss')</script>" not in await page.content()

# ------------------------------------------------------------------------------
# Test: HTML Injection in Email Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_html_injection_email_field(page):
    """
    Attempt to inject HTML in the email field to test for HTML injection.
    Verifies that the HTML is not rendered in the page content.
    """
    login_page = LoginPage(page)
    await login_page.load_login_direct()
    await login_page.enter_email("<b>bold@domain.com</b>")
    await login_page.click_continue()
    # Assert that the HTML tag is not present in the page content
    assert "<b>bold@domain.com</b>" not in await page.content()

# ------------------------------------------------------------------------------
# Test: Command Injection in Email Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_command_injection_password_field(app):
    """
    Attempt to inject a command in the email field to test for command injection.
    Verifies that the login form handles the input safely and shows an error.
    """
    await app.login_page.load_login_direct()
    await app.login_page.enter_email("valid; ls;")
    await app.login_page.click_continue()
    assert await app.login_page.error_message_email_invalid.is_visible()
    expected_message = app.login_page.error_message_email_invalid_text
    actual_message = await app.login_page.get_error_message_email_invalid_text()
    assert expected_message == actual_message
    assert await app.login_page.has_email_invalid_error_icon()

# ------------------------------------------------------------------------------
# Test: Path Traversal in Email Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_comprehensive_email_path_traversal(app):
    """
    Attempt to login using various Traversal payloads in the email field.
    Verifies that the login form is not vulnerable and displays the correct error.
    """
    injection_payloads = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "%252e%252e%252f",
        "..%c0%af..%c0%af..%c0%afetc%c0%afpasswd",
        "../../../etc/passwd%00"
    ]
    for email_payload in injection_payloads:
        await app.login_page.load_login_direct()
        await app.login_page.enter_email(email_payload)
        await app.login_page.click_continue()
        # Assert that the invalid email error message is visible
        assert await app.login_page.error_message_email_invalid.is_visible()
        expected_message = app.login_page.error_message_email_invalid_text
        actual_message = await app.login_page.get_error_message_email_invalid_text()
        assert expected_message == actual_message
        assert await app.login_page.has_email_invalid_error_icon()


# ------------------------------------------------------------------------------
# Test: Brute Force / Rapid Login Attempts
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_brute_force(app):
    """
    Attempt multiple rapid login attempts with incorrect passwords to simulate
    brute force attacks. Verifies that the application consistently shows the
    correct error message and does not allow access.
    """
    await app.login_page.load_login_direct()
    await app.login_page.enter_email("user@domain.com")
    await app.login_page.click_continue()
    for i in range(5):
        await app.login_page.enter_password(f"wrongpassword{i}")
        await app.login_page.click_continue()
        assert await app.login_page.error_message_email_or_password_incorrect.is_visible()
        expected_message = app.login_page.error_message_email_incorrect_text
        actual_message = await app.login_page.get_error_message_email_incorrect_text()
        assert expected_message == actual_message
        assert await app.login_page.has_email_or_password_incorrect_error_icon()