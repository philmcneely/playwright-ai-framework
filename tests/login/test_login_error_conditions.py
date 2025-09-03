"""
===============================================================================
Login Validation Tests for The Internet Test Site
===============================================================================

This module contains tests that verify The Internet test site's login page
validation, error handling, and user experience functionality.

Features:
    ✓ Tests for invalid credentials, empty fields, and malformed inputs
    ✓ Verifies proper error messages and user feedback for various scenarios
    ✓ Tests account blocking functionality after multiple failed attempts
    ✓ Validates password masking/unmasking functionality
    ✓ Tests email editing and correction workflows
    ✓ Comprehensive input validation and error state testing

Error Condition Categories:
    • Invalid Credentials: Testing wrong username/password combinations
    • Empty Fields: Validation of required field enforcement
    • Malformed Inputs: Testing with invalid email formats and special characters
    • Account Security: Rate limiting and brute force protection testing
    • User Experience: Error message clarity and form interaction testing

Usage Example:
    pytest tests/login/test_login_error_conditions.py

Conventions:
    - Each test is marked as async and uses Playwright's async API
    - Test data uses test_data module for valid credentials and inline data for invalid cases
    - Comments explain the purpose and steps of each test
    - Assertions check for expected error messages and UI behavior

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
# Test: Valid Account with Invalid Password
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.compatibility
@pytest.mark.asyncio
async def test_login_invalid_password(app):
    """
    Test login with a valid email but incorrect password.
    Verifies that the appropriate error message is displayed.
    """
    await app.login_page.load_login_direct()
    await app.login_page.enter_email(PERSONAS["user"]["email"])
    await app.login_page.click_continue()
    await app.login_page.enter_password("wrongpassword")
    await app.login_page.click_continue()
    # Assert error message for incorrect password is visible
    assert await app.login_page.error_message_email_or_password_incorrect.is_visible()
    assert app.login_page.error_message_password_incorrect_text == await app.login_page.get_error_message_password_incorrect_text()
    assert await app.login_page.has_email_or_password_incorrect_error_icon()

# ------------------------------------------------------------------------------
# Test: Invalid Email Account
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_invalid_email(app):
    """
    Test login with an invalid/non-existent email address.
    Verifies that the appropriate error message is displayed.
    """
    await app.login_page.load_login_direct()
    await app.login_page.enter_email("dadfdf@gmail.com")
    await app.login_page.click_continue()
    await app.login_page.enter_password("wrongpassword")
    await app.login_page.click_continue()
    # Assert error message for incorrect email is visible
    assert await app.login_page.error_message_email_or_password_incorrect.is_visible()
    expected_message = app.login_page.error_message_email_incorrect_text
    actual_message = await app.login_page.get_error_message_email_incorrect_text()
    assert expected_message == actual_message
    assert await app.login_page.has_email_or_password_incorrect_error_icon()

# ------------------------------------------------------------------------------
# Test: Account Blocking After Multiple Failed Attempts
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.danger
@pytest.mark.login
@pytest.mark.asyncio
async def test_account_blocked_after_multiple_attempts(app):
    """
    Test that an account gets blocked after multiple failed login attempts.
    This test is marked as 'danger' as it can lock out the test account.
    """
    # Simulate multiple failed login attempts (assuming 10+ attempts trigger the block) #hrmmmmm blocked myslef but this 10 doesnt seem to work, need to fix?
    for _ in range(11):
        await app.login_page.load_login_direct()
        await app.login_page.enter_email(PERSONAS["user"]["email"])
        await app.login_page.click_continue()
        await app.login_page.enter_password("wrongpassword")
        await app.login_page.click_continue()
    
    # Wait for blocked account alert to appear
    await app.login_page.blocked_account_alert.wait_for(state="visible", timeout=5000) #need to mabe navigate back to main login?
    
    # Verify account is blocked and message is correct
    assert await app.login_page.is_account_blocked()
    expected_message = app.login_page.blocked_account_alert_text
    actual_message = await app.login_page.get_blocked_account_text()
    assert expected_message == actual_message

# ------------------------------------------------------------------------------
# Test: Empty Email Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_empty_email(app):
    """
    Test login attempt with an empty email field.
    Verifies that the required field error message is displayed.
    """
    await app.login_page.load_login_direct()
    await app.login_page.enter_email("")
    await app.login_page.click_continue()
    # Assert error message for required email field is visible
    assert await app.login_page.error_message_email_required.is_visible()
    expected_message = app.login_page.error_message_email_required_text
    actual_message = await app.login_page.get_error_message_email_required_text()
    assert expected_message == actual_message
    assert await app.login_page.has_email_required_error_icon()

# ------------------------------------------------------------------------------
# Test: Empty Password Field
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_empty_password(app):
    """
    Test login attempt with a valid email but empty password field.
    Verifies that the required field error message is displayed.
    """
    await app.login_page.load_login_direct()
    await app.login_page.enter_email("valid@email.com")
    await app.login_page.click_continue()
    await app.login_page.enter_password("")
    await app.login_page.click_continue()
    # Assert error message for required password field is visible
    assert await app.login_page.error_message_password_required.is_visible()
    expected_message = app.login_page.error_message_password_required_text
    actual_message = await app.login_page.get_error_message_password_required_text()
    assert expected_message == actual_message
    assert await app.login_page.has_password_required_error_icon()

# ------------------------------------------------------------------------------
# Test: Malformed Email Entry
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.compatibility
@pytest.mark.asyncio
async def test_login_malformed_email_just_text(app):
    """
    Test login with malformed email (just text without @ or domain), numbers, 
    single number, a single special character, spaces and unicode.
    Verifies that the email validation error is displayed and password field is not shown.
    I will leave seperate tests for too long a string.
    """
    email_payloads = [
        "asdaqdasf",
        "12345",
        "1",
        "@",
        "dadfdf_)_)&*^*(^)*&%%&^I$%$^#^$$@gmail.com",
        "        ",
        "用户名"
    ]
    for email_payload in email_payloads:
        await app.login_page.load_login_direct()
        await app.login_page.enter_email(email_payload)
        await app.login_page.click_continue()
        # Assert that the invalid email error message is visible
        assert not await app.login_page.password_textbox.is_visible()
        assert await app.login_page.error_message_email_invalid.is_visible()
        expected_message = app.login_page.error_message_email_invalid_text
        actual_message = await app.login_page.get_error_message_email_invalid_text()
        assert expected_message == actual_message
        assert await app.login_page.has_email_invalid_error_icon()

# ------------------------------------------------------------------------------
# Test: Edit Invalid Email to Valid Email
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_edit_invalid_account(app):
    """
    Test the workflow of entering an invalid email, then editing it to a valid one
    and completing the login process successfully.
    """
    await app.login_page.load_login_direct()
    await app.login_page.enter_email("valid@email.com")
    await app.login_page.click_continue()
    # Verify password field is visible for the initial email
    assert await app.login_page.password_textbox.is_visible()
    # Edit the email to a valid account
    await app.login_page.edit_email_link.click()
    await app.login_page.enter_email(PERSONAS["user"]["email"])
    await app.login_page.click_continue()
    await app.login_page.enter_password(PERSONAS["user"]["password"])
    await app.login_page.click_continue()
    await app.dashboard_page.verify_user_profile_info()

# ------------------------------------------------------------------------------
# Test: Email with Too Many Characters (300+)
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_email_too_long(app):
    """
    Test login with an email that exceeds the maximum character limit (300 characters).
    Verifies that the email validation error is displayed.
    """
    await app.login_page.load_login_direct()
    too_long_email_string = "s0F9OjxlA1g2aCxKK9xV2FBvbprskrqaWI8y64DqnVL7yn2rbfoCKod5F8LcqQiMXLhlrn5sMlU87vgr6F4wG3q1FX4dfCcRotpjRx2yQcJsyIpSaUqXraUPmO4K4cag96wREf3zmqcgrZ7ZeETsIFguyR9NG9KTfcX54eox4CoBHKTepsE8OPZaHpFE9tmtyjGWb69PtWcvQp28D6WslyI2sLFV97lQSQyLgdj7LBt9F4BhdW5Uw9fqSSs6bCDTatKbej6qhyXgkftxPMkyPaixRda0uJ5UZbKyASfnxQO7"
    await app.login_page.enter_email(too_long_email_string)
    await app.login_page.click_continue()
    # Assert email validation error is shown
    assert await app.login_page.error_message_email_invalid.is_visible()
    expected_message = app.login_page.error_message_email_invalid_text
    actual_message = await app.login_page.get_error_message_email_invalid_text()
    assert expected_message == actual_message
    assert await app.login_page.has_email_invalid_error_icon()

# ------------------------------------------------------------------------------
# Test: Password with Too Many Characters (300+)
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_login_password_too_long(app):
    """
    Test login with a password that exceeds the maximum character limit (300 characters).
    Verifies that the login fails with appropriate error message.
    """
    await app.login_page.load_login_direct()
    too_long_password_string = "s0F9OjxlA1g2aCxKK9xV2FBvbprskrqaWI8y64DqnVL7yn2rbfoCKod5F8LcqQiMXLhlrn5sMlU87vgr6F4wG3q1FX4dfCcRotpjRx2yQcJsyIpSaUqXraUPmO4K4cag96wREf3zmqcgrZ7ZeETsIFguyR9NG9KTfcX54eox4CoBHKTepsE8OPZaHpFE9tmtyjGWb69PtWcvQp28D6WslyI2sLFV97lQSQyLgdj7LBt9F4BhdW5Uw9fqSSs6bCDTatKbej6qhyXgkftxPMkyPaixRda0uJ5UZbKyASfnxQO7"
    await app.login_page.enter_email("valid@gmail.com")
    await app.login_page.click_continue()
    await app.login_page.enter_password(too_long_password_string)
    await app.login_page.click_continue()
    # Assert password error is shown
    assert await app.login_page.error_message_email_or_password_incorrect.is_visible()
    assert app.login_page.error_message_email_incorrect_text == await app.login_page.get_error_message_password_incorrect_text()
    assert await app.login_page.has_email_or_password_incorrect_error_icon()

# ------------------------------------------------------------------------------
# Test: Password Masking/Unmasking Functionality
# ------------------------------------------------------------------------------

@screenshot_on_failure
@pytest.mark.login
@pytest.mark.asyncio
async def test_password_shown_when_button_clicked(app):
    """
    Test the password show/hide functionality to ensure passwords are properly masked
    and can be revealed when the show password button is clicked.
    """
    await app.login_page.load_login_direct()
    await app.login_page.enter_email(PERSONAS["user"]["email"])
    await app.login_page.click_continue()
    await app.login_page.enter_password("supersecret")

    # Ensure password is hidden by default (type="password")
    input_type = await app.login_page.password_textbox.get_attribute("type")
    assert input_type == "password"

    # Click the show password button to reveal the password
    await app.login_page.show_password_button.click()
    input_type_after = await app.login_page.password_textbox.get_attribute("type")
    assert input_type_after == "text"
    password_text = await app.login_page.get_password_text()
    assert password_text == "supersecret"

    # Click again to hide the password
    await app.login_page.show_password_button.click()
    input_type_hidden = await app.login_page.password_textbox.get_attribute("type")
    assert input_type_hidden == "password"