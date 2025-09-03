"""
===============================================================================
Login Flow and Navigation Tests for The Internet Test Site
===============================================================================

This module contains tests that verify The Internet test site's login flows,
navigation paths, and authentication functionality including both successful
and failed login scenarios.

Features:
    ✓ Tests for login entry point (direct navigation)
    ✓ Verifies successful login with valid credentials
    ✓ Tests invalid credential scenarios and error handling
    ✓ Validates logout functionality and session management
    ✓ Tests form interactions and user experience

Usage Example:
    pytest tests/login/test_login.py

Conventions:
    - Each test is marked as async and uses Playwright's async API
    - Test data uses predefined users from test_data module
    - Comments explain the purpose and steps of each test
    - Tests handle both success and failure scenarios properly

Author: Playwright AI Test Framework
Site: The Internet (https://the-internet.herokuapp.com)
Date: [2025-09-03]
===============================================================================
"""

import pytest
from pages.app import App
from test_data.test_data import INVALID_USERS, EXPECTED_MESSAGES
from utils.decorators.screenshot_decorator import screenshot_on_failure
from utils.debug import debug_print


# ------------------------------------------------------------------------------
# Test: Successful Login Flow
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.smoke
@pytest.mark.asyncio
async def test_login_direct_valid_credentials(page):
    """
    Test direct login navigation with valid credentials.
    Verifies successful login and navigation to secure area.
    """
    debug_print("Starting valid login test")
    app = App(page)
    
    await app.login.navigate()
    await app.login.login_with_demo_user()
    
    # Verify successful login by checking secure page
    assert await app.secure.is_on_secure_page()
    
    # Verify flash message indicates success
    flash_text = await app.secure.get_flash_message()
    assert "You logged into a secure area!" in flash_text
    
    debug_print("Valid login test completed successfully")


# ------------------------------------------------------------------------------
# Test: Invalid Username Scenario
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_invalid_username(page):
    """
    Test login with invalid username.
    Verifies error handling and user feedback.
    """
    debug_print("Starting invalid username test")
    app = App(page)
    
    await app.login.navigate()
    await app.login.login(
        INVALID_USERS["invalid_username"]["username"],
        INVALID_USERS["invalid_username"]["password"]
    )
    
    # Should remain on login page
    assert await app.login.is_on_login_page()
    
    # Verify error message
    flash_text = await app.login.get_flash_message()
    assert EXPECTED_MESSAGES["invalid_username"] in flash_text
    
    debug_print("Invalid username test completed")


# ------------------------------------------------------------------------------
# Test: Invalid Password Scenario
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_invalid_password(page):
    """
    Test login with invalid password.
    Verifies error handling for wrong password.
    """
    debug_print("Starting invalid password test")
    app = App(page)
    
    await app.login.navigate()
    await app.login.login(
        INVALID_USERS["invalid_password"]["username"],
        INVALID_USERS["invalid_password"]["password"]
    )
    
    # Should remain on login page
    assert await app.login.is_on_login_page()
    
    # Verify error message
    flash_text = await app.login.get_flash_message()
    assert EXPECTED_MESSAGES["invalid_password"] in flash_text
    
    debug_print("Invalid password test completed")


# ------------------------------------------------------------------------------
# Test: Empty Credentials Scenario
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_empty_credentials(page):
    """
    Test login with empty username and password.
    Verifies validation handling for empty fields.
    """
    debug_print("Starting empty credentials test")
    app = App(page)
    
    await app.login.navigate()
    await app.login.login("", "")
    
    # Should remain on login page
    assert await app.login.is_on_login_page()
    
    debug_print("Empty credentials test completed")


# ------------------------------------------------------------------------------
# Test: Logout Functionality
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_logout_functionality(page):
    """
    Test logout functionality after successful login.
    Verifies complete login-logout workflow.
    """
    debug_print("Starting logout functionality test")
    app = App(page)
    
    # First login successfully
    await app.login.navigate()
    await app.login.login_with_demo_user()
    assert await app.secure.is_on_secure_page()
    
    # Then logout
    await app.secure.logout()
    
    # Should be back on login page
    assert await app.login.is_on_login_page()
    
    # Verify logout message
    flash_text = await app.login.get_flash_message()
    assert "You logged out of the secure area!" in flash_text
    
    debug_print("Logout functionality test completed")


# ------------------------------------------------------------------------------
# Test: Form Field Validation
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_form_field_validation(page):
    """
    Test form field interactions and validation.
    Verifies field behavior and user experience.
    """
    debug_print("Starting form field validation test")
    app = App(page)
    
    await app.login.navigate()
    
    # Test individual field interactions
    await app.login.enter_username("test_user")
    username_value = await app.login.get_username_value()
    assert username_value == "test_user"
    
    await app.login.enter_password("test_password")
    # Note: Password field value typically can't be read for security
    
    # Clear fields
    await app.login.clear_username()
    await app.login.clear_password()
    
    username_value = await app.login.get_username_value()
    assert username_value == ""
    
    debug_print("Form field validation test completed")
