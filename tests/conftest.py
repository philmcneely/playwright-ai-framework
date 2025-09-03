"""
===============================================================================
Pytest Configuration and Fixtures
===============================================================================

This module contains pytest configuration, fixtures, and shared test utilities
for the Hudl application test suite. It provides centralized fixture definitions
that are available across all test modules.

Features:
    ✓ App fixture that aggregates all page objects for easy test access.
    ✓ Login page fixture with automatic navigation for login-specific tests.
    ✓ Environment variable loading for configuration management.
    ✓ Centralized fixture management to avoid code duplication.

Usage Example:
    # Fixtures are automatically available in all test files
    @pytest.mark.asyncio
    async def test_something(app):
        await app.login_page.enter_email("user@example.com")
        await app.dashboard_page.verify_user_info()

Conventions:
    - All fixtures are async to maintain Playwright compatibility.
    - The app fixture provides access to all page objects through a single instance.
    - Environment variables are loaded once at module level.
    - Fixtures follow the naming convention of the classes they instantiate.

Author: PMAC
Date: [2025-07-27]
===============================================================================
"""

import pytest
from pages.login_page import LoginPage
from pages.app import App

# ------------------------------------------------------------------------------
# Login Page Fixture with Auto-Navigation
# ------------------------------------------------------------------------------

@pytest.fixture
async def login_page(page):
    """
    Fixture that provides a LoginPage instance with automatic navigation
    to the login page. Useful for tests that focus specifically on login functionality.
    
    Args:
        page: Playwright page fixture
        
    Returns:
        LoginPage: Configured login page object with navigation completed
    """
    login_page = LoginPage(page)
    await login_page.load_login_direct()
    return login_page

# ------------------------------------------------------------------------------
# App Fixture - Central Page Object Aggregator
# ------------------------------------------------------------------------------

@pytest.fixture
async def app(page):
    """
    Fixture that provides an App instance containing all page objects.
    This is the primary fixture for most tests, eliminating the need
    to pass multiple page fixtures to test functions.
    
    Args:
        page: Playwright page fixture
        
    Returns:
        App: Application object with access to all page objects
        
    Usage:
        Any pages configured in pages/app.py will be available here through
        the app fixture (e.g., app.login_page, app.dashboard_page, etc.)
    """
    return App(page)