"""
===============================================================================
App Class for The Internet Test Site
===============================================================================
This module defines the App class, which serves as a central aggregator for all
page objects in The Internet test site automation suite. It provides a single
entry point for accessing all page objects, eliminating the need to pass
multiple page fixtures to test functions.

Features:
    ✓ Centralized access to all page objects through a single class
    ✓ Eliminates the need for multiple page fixtures in test functions
    ✓ Clean and organized approach to managing page objects
    ✓ Easy to extend with new page objects as the test suite grows
    ✓ Maintains separation of concerns while providing convenience

Usage Example:
    from pages.app import App
    
    @pytest.mark.asyncio
    async def test_login_flow(app):
        await app.login_page.navigate()
        await app.login_page.enter_username("tomsmith")
        await app.login_page.enter_password("SuperSecretPassword!")
        await app.login_page.click_login()
        
        # Access secure page through same app instance
        assert await app.secure_page.is_on_secure_page()

Conventions:
    - All page objects are instantiated in __init__ for immediate availability
    - Page objects are stored as instance attributes for easy access
    - No async operations are performed in __init__ to avoid fixture issues
    - New page objects should be added as attributes following the same pattern

Author: PMAC
Site: The Internet (https://the-internet.herokuapp.com)
===============================================================================
"""
from pages.login_page import LoginPage
from pages.secure_page import SecurePage


class App:
    def __init__(self, page):
        self.page = page
        self.login_page = LoginPage(page)
        self.secure_page = SecurePage(page)
