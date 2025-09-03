"""
===============================================================================
Login Flow and Navigation Tests for The Internet Test Site
===============================================================================
This module contains tests that verify The Internet test site's login flows,
navigation paths, and authentication functionality including both successful
and failed login scenarios.

Features:
    ✓ Tests for valid login with demo user credentials
    ✓ Verifies unsuccessful login attempts with invalid credentials
    ✓ Tests empty credential handling and validation
    ✓ Validates logout functionality and session management
    ✓ Tests form field interactions and user experience

Usage Example:
    pytest tests/test_login.py
    pytest tests/test_login.py -m smoke

Conventions:
    - Each test is marked as async and uses Playwright's async API
    - Test data uses predefined users from test_data module
    - Comments explain the purpose and steps of each test
    - All tests verify both UI state and underlying functionality

Author: Playwright AI Test Framework
Site: The Internet (https://the-internet.herokuapp.com)
Date: [2025-09-03]
===============================================================================
"""
import pytest
from pages.app import App
from test_data.test_data import INVALID_USERS, EXPECTED_MESSAGES
from utils.debug import debug_print


class TestLogin:
    """Test suite for login functionality."""
    
    @pytest.mark.smoke
    async def test_valid_login(self, page):
        """Test successful login with valid credentials."""
        debug_print("Starting valid login test")
        
        app = App(page)
        
        # Navigate to login page
        await app.login.navigate()
        
        # Verify login page is loaded
        assert await app.login.is_username_field_visible()
        assert await app.login.is_password_field_visible()
        assert await app.login.is_login_button_visible()
        
        # Login with demo user
        await app.login.login_with_demo_user()
        
        # Verify successful login
        assert await app.secure.verify_successful_login()
        assert await app.secure.is_on_secure_page()
        
        # Verify success message
        flash_message = await app.secure.get_flash_message()
        assert EXPECTED_MESSAGES["login_success"] in flash_message
        
        debug_print("Valid login test completed successfully")
    
    @pytest.mark.smoke
    async def test_invalid_username(self, page):
        """Test login with invalid username."""
        debug_print("Starting invalid username test")
        
        app = App(page)
        invalid_user = INVALID_USERS["invalid_username"]
        
        # Navigate to login page
        await app.login.navigate()
        
        # Login with invalid username
        await app.login.login(
            invalid_user["username"],
            invalid_user["password"]
        )
        
        # Verify login failed
        assert not await app.secure.is_on_secure_page()
        assert await app.login.is_error_displayed()
        
        # Verify error message
        flash_message = await app.login.get_flash_message()
        assert EXPECTED_MESSAGES["login_failure"] in flash_message
        
        debug_print("Invalid username test completed successfully")
    
    @pytest.mark.smoke
    async def test_invalid_password(self, page):
        """Test login with invalid password."""
        debug_print("Starting invalid password test")
        
        app = App(page)
        invalid_user = INVALID_USERS["invalid_password"]
        
        # Navigate to login page
        await app.login.navigate()
        
        # Login with invalid password
        await app.login.login(
            invalid_user["username"],
            invalid_user["password"]
        )
        
        # Verify login failed
        assert not await app.secure.is_on_secure_page()
        assert await app.login.is_error_displayed()
        
        # Verify error message contains password invalid text
        flash_message = await app.login.get_flash_message()
        assert EXPECTED_MESSAGES["password_invalid"] in flash_message
        
        debug_print("Invalid password test completed successfully")
    
    @pytest.mark.smoke
    async def test_empty_credentials(self, page):
        """Test login with empty username and password."""
        debug_print("Starting empty credentials test")
        
        app = App(page)
        empty_user = INVALID_USERS["both_empty"]
        
        # Navigate to login page
        await app.login.navigate()
        
        # Attempt login with empty credentials
        await app.login.login(
            empty_user["username"],
            empty_user["password"]
        )
        
        # Verify login failed
        assert not await app.secure.is_on_secure_page()
        assert await app.login.is_error_displayed()
        
        debug_print("Empty credentials test completed successfully")
    
    @pytest.mark.regression
    async def test_logout_functionality(self, page):
        """Test logout functionality after successful login."""
        debug_print("Starting logout functionality test")
        
        app = App(page)
        
        # Login first
        await app.login.navigate()
        await app.login.login_with_demo_user()
        
        # Verify successful login
        assert await app.secure.verify_successful_login()
        
        # Logout
        await app.secure.logout()
        
        # Verify logout was successful (back to login page)
        flash_message = await app.login.get_flash_message()
        assert EXPECTED_MESSAGES["logout_success"] in flash_message
        
        # Verify we're back on login page
        assert await app.login.is_username_field_visible()
        assert await app.login.is_login_button_visible()
        
        debug_print("Logout functionality test completed successfully")
    
    @pytest.mark.regression
    async def test_form_field_validation(self, page):
        """Test form field interactions and validation."""
        debug_print("Starting form field validation test")
        
        app = App(page)
        
        # Navigate to login page
        await app.login.navigate()
        
        # Test form field interactions
        test_username = "test_user"
        test_password = "test_pass"
        
        # Fill and verify fields
        await app.login.fill_text(app.login.username_input, test_username)
        await app.login.fill_text(app.login.password_input, test_password)
        
        # Verify field values
        assert await app.login.get_username_value() == test_username
        assert await app.login.get_password_value() == test_password
        
        # Clear form
        await app.login.clear_form()
        
        # Verify fields are cleared
        assert await app.login.get_username_value() == ""
        assert await app.login.get_password_value() == ""
        
        debug_print("Form field validation test completed successfully")
