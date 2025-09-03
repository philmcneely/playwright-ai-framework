"""
===============================================================================
Login Validation Tests for The Internet Test Site
===============================================================================

This module contains tests that verify The Internet test site's login page
validation, error handling, and user experience functionality.

Features:
    ✓ Tests for invalid credentials, empty fields, and malformed inputs
    ✓ Verifies proper error messages and user feedback for various scenarios
    ✓ Tests multiple login entry points (direct and via navigation)
    ✓ Validates form field behavior and interactions
    ✓ Comprehensive input validation and error state testing

Error Condition Categories:
    • Invalid Credentials: Testing wrong username/password combinations
    • Empty Fields: Validation of required field enforcement
    • Multiple Entry Points: Direct login vs home page navigation
    • Form Interactions: Field clearing, input validation
    • User Experience: Error message clarity and form behavior

Usage Example:
    pytest tests/login/test_login_error_conditions.py

Conventions:
    - Each test is marked as async and uses Playwright's async API
    - Test data uses test_data module for valid/invalid credential combinations
    - Comments explain the purpose and steps of each test
    - Assertions check for expected error messages and UI behavior

Author: PMAC
Site: The Internet (https://the-internet.herokuapp.com)
Date: [2025-09-03]
===============================================================================
"""

import pytest
from data.test_data import INVALID_USERS, EXPECTED_MESSAGES
from utils.decorators.screenshot_decorator import screenshot_on_failure
from utils.debug import debug_print


# ------------------------------------------------------------------------------
# Test: Invalid Username (Direct Login)
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_invalid_username_direct(app):
    """
    Test login with invalid username via direct navigation to login page.
    Verifies that the appropriate error message is displayed.
    """
    debug_print("Testing invalid username via direct login")
    
    # Navigate directly to login page
    await app.login_page.navigate()
    
    # Attempt login with invalid username
    await app.login_page.login(
        INVALID_USERS["invalid_username"]["username"],
        INVALID_USERS["invalid_username"]["password"]
    )
    
    # Should remain on login page
    assert await app.login_page.is_on_login_page()
    
    # Verify error message
    flash_text = await app.login_page.get_flash_message()
    assert EXPECTED_MESSAGES["invalid_username"] in flash_text
    
    debug_print("Invalid username test (direct) completed")


# ------------------------------------------------------------------------------
# Test: Invalid Username (Home Navigation)
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_invalid_username_via_home(app):
    """
    Test login with invalid username via home page navigation.
    Verifies navigation flow and error handling.
    """
    debug_print("Testing invalid username via home navigation")
    
    # Navigate to home page first, then to login
    await app.page.goto("https://the-internet.herokuapp.com")
    await app.page.click('a[href="/login"]')
    
    # Verify we're on login page
    assert await app.login_page.is_on_login_page()
    
    # Attempt login with invalid username
    await app.login_page.login(
        INVALID_USERS["invalid_username"]["username"],
        INVALID_USERS["invalid_username"]["password"]
    )
    
    # Verify error message
    flash_text = await app.login_page.get_flash_message()
    assert EXPECTED_MESSAGES["invalid_username"] in flash_text
    
    debug_print("Invalid username test (via home) completed")


# ------------------------------------------------------------------------------
# Test: Invalid Password (Direct Login)
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_invalid_password_direct(app):
    """
    Test login with valid username but incorrect password.
    Verifies that the appropriate error message is displayed.
    """
    debug_print("Testing invalid password via direct login")
    
    await app.login_page.navigate()
    await app.login_page.login(
        INVALID_USERS["invalid_password"]["username"],
        INVALID_USERS["invalid_password"]["password"]
    )
    
    # Should remain on login page
    assert await app.login_page.is_on_login_page()
    
    # Verify error message
    flash_text = await app.login_page.get_flash_message()
    assert EXPECTED_MESSAGES["invalid_password"] in flash_text
    
    debug_print("Invalid password test completed")


# ------------------------------------------------------------------------------
# Test: Empty Username Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_empty_username(app):
    """
    Test login attempt with an empty username field.
    Verifies that the form handles empty username appropriately.
    """
    debug_print("Testing empty username field")
    
    await app.login_page.navigate()
    await app.login_page.login("", "somepassword")
    
    # Should remain on login page
    assert await app.login_page.is_on_login_page()
    
    debug_print("Empty username test completed")


# ------------------------------------------------------------------------------
# Test: Empty Password Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_empty_password(app):
    """
    Test login attempt with empty password field.
    Verifies that the form handles empty password appropriately.
    """
    debug_print("Testing empty password field")
    
    await app.login_page.navigate()
    await app.login_page.login("someusername", "")
    
    # Should remain on login page
    assert await app.login_page.is_on_login_page()
    
    debug_print("Empty password test completed")


# ------------------------------------------------------------------------------
# Test: Both Fields Empty
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_empty_credentials(app):
    """
    Test login attempt with both username and password empty.
    Verifies that the form handles completely empty submission.
    """
    debug_print("Testing both fields empty")
    
    await app.login_page.navigate()
    await app.login_page.login("", "")
    
    # Should remain on login page
    assert await app.login_page.is_on_login_page()
    
    debug_print("Empty credentials test completed")


# ------------------------------------------------------------------------------
# Test: Form Field Interactions
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_form_field_clearing_and_retry(app):
    """
    Test workflow of entering invalid data, clearing, and retrying.
    Verifies form field manipulation and retry behavior.
    """
    debug_print("Testing form field clearing and retry")
    
    await app.login_page.navigate()
    
    # Enter invalid data first
    await app.login_page.enter_username("invalid_user")
    await app.login_page.enter_password("invalid_pass")
    
    # Verify data was entered
    username_value = await app.login_page.get_username_value()
    assert username_value == "invalid_user"
    
    # Clear fields
    await app.login_page.clear_username()
    await app.login_page.clear_password()
    
    # Verify fields are cleared
    username_value = await app.login_page.get_username_value()
    assert username_value == ""
    
    # Now try with valid credentials
    await app.login_page.login_with_demo_user()
    
    # Should succeed and navigate to secure area
    assert await app.secure_page.is_on_secure_page()
    
    debug_print("Form field clearing and retry test completed")


# ------------------------------------------------------------------------------
# Test: Special Characters in Username
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_special_characters_username(app):
    """
    Test login with special characters in username field.
    Verifies that special characters are handled appropriately.
    """
    debug_print("Testing special characters in username")
    
    await app.login_page.navigate()
    
    special_usernames = [
        "user@domain.com",
        "user!@#$%",
        "用户名",  # Unicode characters
        "user with spaces",
        "user'with\"quotes"
    ]
    
    for username in special_usernames:
        await app.login_page.enter_username(username)
        await app.login_page.enter_password("somepassword")
        await app.login_page.click_element(app.login_page.login_button)
        
        # Should remain on login page for all invalid usernames
        assert await app.login_page.is_on_login_page()
        
        # Clear for next iteration
        await app.login_page.clear_username()
        await app.login_page.clear_password()
    
    debug_print("Special characters username test completed")


# ------------------------------------------------------------------------------
# Test: Very Long Input Strings
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_very_long_inputs(app):
    """
    Test login with very long username and password strings.
    Verifies that the form handles excessive input lengths gracefully.
    """
    debug_print("Testing very long input strings")
    
    await app.login_page.navigate()
    
    # Create very long strings
    long_username = "a" * 500
    long_password = "b" * 500
    
    await app.login_page.login(long_username, long_password)
    
    # Should remain on login page
    assert await app.login_page.is_on_login_page()
    
    debug_print("Very long inputs test completed")


# ------------------------------------------------------------------------------
# Test: Multiple Failed Attempts
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_multiple_failed_login_attempts(app):
    """
    Test multiple consecutive failed login attempts.
    Verifies that the system handles repeated failures appropriately.
    """
    debug_print("Testing multiple failed login attempts")
    
    await app.login_page.navigate()
    
    # Attempt multiple failed logins
    for i in range(3):
        await app.login_page.login(f"invalid_user_{i}", f"invalid_pass_{i}")
        
        # Should remain on login page each time
        assert await app.login_page.is_on_login_page()
        
        # May have flash message
        flash_text = await app.login_page.get_flash_message()
        debug_print(f"Attempt {i+1}: Flash message = {flash_text}")
    
    debug_print("Multiple failed attempts test completed")
