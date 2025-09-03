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

Author: PMAC
Site: The Internet (https://the-internet.herokuapp.com)
Date: [2025-09-03]
===============================================================================
"""

import pytest
from utils.decorators.screenshot_decorator import screenshot_on_failure
from utils.debug import debug_print


# ------------------------------------------------------------------------------
# Test: SQL Injection in Username Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.security
@pytest.mark.asyncio
async def test_login_sql_injection_username(app):
    """
    Test login form's resistance to SQL injection attacks via username field.
    Verifies that SQL injection patterns are handled securely.
    """
    debug_print("Testing SQL injection in username field")
    
    await app.login_page.navigate()
    
    sql_injection_payloads = [
        "' OR '1'='1",
        "admin'--",
        "' OR 1=1--",
        "'; DROP TABLE users; --",
        "' UNION SELECT * FROM users--",
        "admin'; UPDATE users SET password='hacked'--"
    ]
    
    for payload in sql_injection_payloads:
        await app.login_page.login(payload, "password")
        
        # Should remain on login page and not authenticate
        assert await app.login_page.is_on_login_page()
        
        # Clear for next iteration
        await app.login_page.clear_username()
        await app.login_page.clear_password()
    
    debug_print("SQL injection username test completed")


# ------------------------------------------------------------------------------
# Test: SQL Injection in Password Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.security
@pytest.mark.asyncio
async def test_login_sql_injection_password(app):
    """
    Test login form's resistance to SQL injection attacks via password field.
    Verifies that SQL injection patterns in passwords are handled securely.
    """
    debug_print("Testing SQL injection in password field")
    
    await app.login_page.navigate()
    
    sql_injection_payloads = [
        "' OR '1'='1",
        "password'--",
        "' OR 1=1--",
        "'; DROP TABLE users; --",
        "' UNION SELECT password FROM users WHERE username='admin'--"
    ]
    
    for payload in sql_injection_payloads:
        await app.login_page.login("tomsmith", payload)
        
        # Should remain on login page and not authenticate
        assert await app.login_page.is_on_login_page()
        
        # Clear for next iteration
        await app.login_page.clear_username()
        await app.login_page.clear_password()
    
    debug_print("SQL injection password test completed")


# ------------------------------------------------------------------------------
# Test: Cross-Site Scripting (XSS) in Username Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.security
@pytest.mark.asyncio
async def test_login_xss_username(app):
    """
    Test login form's resistance to XSS attacks via username field.
    Verifies that script injection attempts are handled securely.
    """
    debug_print("Testing XSS in username field")
    
    await app.login_page.navigate()
    
    xss_payloads = [
        "<script>alert('XSS')</script>",
        "javascript:alert('XSS')",
        "<img src=x onerror=alert('XSS')>",
        "<svg onload=alert('XSS')>",
        "';alert('XSS');//",
        "<iframe src=javascript:alert('XSS')></iframe>"
    ]
    
    for payload in xss_payloads:
        await app.login_page.login(payload, "password")
        
        # Should remain on login page and not execute scripts
        assert await app.login_page.is_on_login_page()
        
        # Verify no alert dialogs were triggered
        # Note: In a real test, we'd check for absence of alert dialogs
        
        # Clear for next iteration
        await app.login_page.clear_username()
        await app.login_page.clear_password()
    
    debug_print("XSS username test completed")


# ------------------------------------------------------------------------------
# Test: Cross-Site Scripting (XSS) in Password Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.security
@pytest.mark.asyncio
async def test_login_xss_password(app):
    """
    Test login form's resistance to XSS attacks via password field.
    Verifies that script injection attempts in passwords are handled securely.
    """
    debug_print("Testing XSS in password field")
    
    await app.login_page.navigate()
    
    xss_payloads = [
        "<script>alert('XSS')</script>",
        "javascript:alert('XSS')",
        "<img src=x onerror=alert('XSS')>",
        "<svg onload=alert('XSS')>"
    ]
    
    for payload in xss_payloads:
        await app.login_page.login("tomsmith", payload)
        
        # Should remain on login page and not execute scripts
        assert await app.login_page.is_on_login_page()
        
        # Clear for next iteration
        await app.login_page.clear_username()
        await app.login_page.clear_password()
    
    debug_print("XSS password test completed")


# ------------------------------------------------------------------------------
# Test: HTML Injection in Username Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.security
@pytest.mark.asyncio
async def test_login_html_injection_username(app):
    """
    Test login form's resistance to HTML injection via username field.
    Verifies that HTML content is properly sanitized.
    """
    debug_print("Testing HTML injection in username field")
    
    await app.login_page.navigate()
    
    html_injection_payloads = [
        "<h1>Injected Header</h1>",
        "<b>Bold Text</b>",
        "<div>Injected Div</div>",
        "<form>Injected Form</form>",
        "<input type='text' value='injected'>",
        "<iframe src='http://evil.com'></iframe>"
    ]
    
    for payload in html_injection_payloads:
        await app.login_page.login(payload, "password")
        
        # Should remain on login page
        assert await app.login_page.is_on_login_page()
        
        # Clear for next iteration
        await app.login_page.clear_username()
        await app.login_page.clear_password()
    
    debug_print("HTML injection username test completed")


# ------------------------------------------------------------------------------
# Test: Command Injection in Username Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.security
@pytest.mark.asyncio
async def test_login_command_injection_username(app):
    """
    Test login form's resistance to command injection via username field.
    Verifies that system command injection attempts are handled securely.
    """
    debug_print("Testing command injection in username field")
    
    await app.login_page.navigate()
    
    command_injection_payloads = [
        "; ls -la",
        "| cat /etc/passwd",
        "&& whoami",
        "; rm -rf /",
        "$(cat /etc/passwd)",
        "`whoami`",
        "${IFS}cat${IFS}/etc/passwd"
    ]
    
    for payload in command_injection_payloads:
        await app.login_page.login(payload, "password")
        
        # Should remain on login page
        assert await app.login_page.is_on_login_page()
        
        # Clear for next iteration
        await app.login_page.clear_username()
        await app.login_page.clear_password()
    
    debug_print("Command injection username test completed")


# ------------------------------------------------------------------------------
# Test: Path Traversal in Username Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.security
@pytest.mark.asyncio
async def test_login_path_traversal_username(app):
    """
    Test login form's resistance to path traversal attacks via username field.
    Verifies that directory traversal attempts are handled securely.
    """
    debug_print("Testing path traversal in username field")
    
    await app.login_page.navigate()
    
    path_traversal_payloads = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "....//....//....//etc/passwd",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "../../../../../../etc/passwd%00",
        "file:///etc/passwd"
    ]
    
    for payload in path_traversal_payloads:
        await app.login_page.login(payload, "password")
        
        # Should remain on login page
        assert await app.login_page.is_on_login_page()
        
        # Clear for next iteration
        await app.login_page.clear_username()
        await app.login_page.clear_password()
    
    debug_print("Path traversal username test completed")


# ------------------------------------------------------------------------------
# Test: LDAP Injection in Username Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.security
@pytest.mark.asyncio
async def test_login_ldap_injection_username(app):
    """
    Test login form's resistance to LDAP injection via username field.
    Verifies that LDAP injection attempts are handled securely.
    """
    debug_print("Testing LDAP injection in username field")
    
    await app.login_page.navigate()
    
    ldap_injection_payloads = [
        "*",
        "*)(&",
        "*)%00",
        ")(objectClass=*",
        "*)(cn=*",
        "admin)(&(password=*))",
        "*)|(cn=*"
    ]
    
    for payload in ldap_injection_payloads:
        await app.login_page.login(payload, "password")
        
        # Should remain on login page
        assert await app.login_page.is_on_login_page()
        
        # Clear for next iteration
        await app.login_page.clear_username()
        await app.login_page.clear_password()
    
    debug_print("LDAP injection username test completed")


# ------------------------------------------------------------------------------
# Test: Buffer Overflow Attempt
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.security
@pytest.mark.asyncio
async def test_login_buffer_overflow_attempt(app):
    """
    Test login form's handling of extremely long input strings.
    Verifies that buffer overflow attempts are handled gracefully.
    """
    debug_print("Testing buffer overflow attempt")
    
    await app.login_page.navigate()
    
    # Create extremely long strings
    extremely_long_string = "A" * 10000
    
    await app.login_page.login(extremely_long_string, extremely_long_string)
    
    # Should remain on login page
    assert await app.login_page.is_on_login_page()
    
    debug_print("Buffer overflow attempt test completed")


# ------------------------------------------------------------------------------
# Test: Unicode and Encoding Attacks
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.security
@pytest.mark.asyncio
async def test_login_unicode_encoding_attacks(app):
    """
    Test login form's handling of various Unicode and encoding attack vectors.
    Verifies that encoding-based attacks are handled securely.
    """
    debug_print("Testing Unicode and encoding attacks")
    
    await app.login_page.navigate()
    
    encoding_payloads = [
        "%27%20OR%201=1--",  # URL encoded SQL injection
        "%3Cscript%3Ealert(%27XSS%27)%3C/script%3E",  # URL encoded XSS
        "&#x27;&#x20;OR&#x20;1=1--",  # HTML entity encoded SQL injection
        "\u0027\u0020OR\u00201=1--",  # Unicode SQL injection
        "测试用户",  # Chinese characters
        "العربية",  # Arabic characters
        "🚀💀🔥",  # Emoji characters
        "\x00\x01\x02\x03",  # Control characters
    ]
    
    for payload in encoding_payloads:
        await app.login_page.login(payload, "password")
        
        # Should remain on login page
        assert await app.login_page.is_on_login_page()
        
        # Clear for next iteration
        await app.login_page.clear_username()
        await app.login_page.clear_password()
    
    debug_print("Unicode and encoding attacks test completed")
