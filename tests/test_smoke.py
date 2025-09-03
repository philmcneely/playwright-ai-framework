"""
===============================================================================
Smoke Tests for The Internet Test Site
===============================================================================
This module contains essential smoke tests that verify basic functionality
and critical user journeys on The Internet test site. These tests serve as
a quick validation suite to ensure the application is functional before
running more comprehensive test suites.

Features:
    ✓ Basic page load verification and accessibility
    ✓ Core navigation and login flow validation
    ✓ Cross-browser compatibility verification
    ✓ Essential user journey testing

Usage Example:
    pytest tests/test_smoke.py
    pytest -m smoke

Conventions:
    - Tests are designed to run quickly and fail fast
    - Each test focuses on critical functionality only
    - All tests are marked with @pytest.mark.smoke
    - Tests should be stable and reliable for CI/CD pipelines

Author: Playwright AI Test Framework
Site: The Internet (https://the-internet.herokuapp.com)
Date: [2025-09-03]
===============================================================================
"""
import pytest
from pages.app import App
from test_data.test_data import TEST_URLS, EXPECTED_MESSAGES
from utils.debug import debug_print


class TestSmoke:
    """Smoke test suite for basic functionality verification."""
    
    @pytest.mark.smoke
    async def test_home_page_loads(self, page):
        """Test that the home page loads successfully."""
        debug_print("Starting home page load test")
        
        app = App(page)
        
        # Navigate to home page
        await app.navigate_to_home()
        
        # Verify page loads
        title = await app.get_page_title()
        assert "The Internet" in title
        
        # Verify URL is correct
        current_url = await app.get_current_url()
        assert TEST_URLS["base"] in current_url
        
        debug_print("Home page load test completed successfully")
    
    @pytest.mark.smoke
    async def test_login_page_accessibility(self, page):
        """Test that login page is accessible and loads correctly."""
        debug_print("Starting login page accessibility test")
        
        app = App(page)
        
        # Navigate to login page
        await app.login.navigate()
        
        # Verify page elements are present
        assert await app.login.is_username_field_visible()
        assert await app.login.is_password_field_visible()
        assert await app.login.is_login_button_visible()
        
        # Verify page title
        page_title = await app.login.get_page_title()
        assert EXPECTED_MESSAGES["login_page_title"] in page_title
        
        debug_print("Login page accessibility test completed successfully")
    
    @pytest.mark.smoke
    async def test_basic_login_flow(self, page):
        """Test basic login and logout flow."""
        debug_print("Starting basic login flow test")
        
        app = App(page)
        
        # Navigate to login page
        await app.login.navigate()
        
        # Perform login
        await app.login.login_with_demo_user()
        
        # Verify successful login
        assert await app.secure.is_on_secure_page()
        assert await app.secure.is_logout_button_visible()
        
        # Verify secure page title
        secure_title = await app.secure.get_page_title()
        assert EXPECTED_MESSAGES["secure_area_title"] in secure_title
        
        # Logout
        await app.secure.logout()
        
        # Verify logout success
        assert await app.login.is_username_field_visible()
        
        debug_print("Basic login flow test completed successfully")
    
    @pytest.mark.smoke
    async def test_page_navigation(self, page):
        """Test navigation between different pages."""
        debug_print("Starting page navigation test")
        
        app = App(page)
        
        # Start from home page
        await app.navigate_to_home()
        home_url = await app.get_current_url()
        assert TEST_URLS["base"] in home_url
        
        # Navigate to login page
        await app.login.navigate()
        login_url = await app.get_current_url()
        assert "login" in login_url
        
        # Login and go to secure page
        await app.login.login_with_demo_user()
        secure_url = await app.get_current_url()
        assert "secure" in secure_url
        
        debug_print("Page navigation test completed successfully")
    
    @pytest.mark.smoke
    async def test_browser_compatibility(self, page):
        """Test basic browser compatibility features."""
        debug_print("Starting browser compatibility test")
        
        app = App(page)
        
        # Navigate to login page
        await app.login.navigate()
        
        # Test JavaScript functionality
        page_title = await page.evaluate("() => document.title")
        assert page_title is not None
        
        # Test CSS loading
        username_field = app.login.username_input
        is_visible = await username_field.is_visible()
        assert is_visible
        
        # Test form submission
        await app.login.login_with_demo_user()
        assert await app.secure.is_on_secure_page()
        
        debug_print("Browser compatibility test completed successfully")
