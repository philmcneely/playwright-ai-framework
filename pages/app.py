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
    async def test_login_flow(page):
        app = App(page)
        await app.login.navigate()
        await app.login.enter_username("tomsmith")
        await app.login.enter_password("SuperSecretPassword!")
        await app.login.click_login()
        
        # Access secure page through same app instance
        assert await app.secure.is_on_secure_page()
        
Dependencies:
    - pages.login_page: LoginPage object
    - pages.secure_page: SecurePage object
    - config.settings: Environment configuration
    - utils.debug: Debug logging utilities

Author: Playwright AI Test Framework
Site: The Internet (https://the-internet.herokuapp.com)
===============================================================================
"""
from playwright.async_api import Page
from pages.login_page import LoginPage
from pages.secure_page import SecurePage
from config.settings import settings
from utils.debug import debug_print


class App:
    """Main application class providing access to all page objects."""
    
    def __init__(self, page: Page):
        self.page = page
        
        # Initialize page objects
        self.login = LoginPage(page)
        self.secure = SecurePage(page)
    
    async def navigate_to_home(self) -> None:
        """Navigate to the home page of The Internet."""
        debug_print(f"Navigating to home page: {settings.BASE_URL}")
        await self.page.goto(settings.BASE_URL)
        await self.page.wait_for_load_state()
    
    async def get_current_url(self) -> str:
        """Get the current page URL."""
        return self.page.url
    
    async def get_page_title(self) -> str:
        """Get the current page title."""
        return await self.page.title()
    
    async def take_screenshot(self, name: str = "app_screenshot") -> bytes:
        """Take a screenshot of the current page."""
        debug_print(f"Taking application screenshot: {name}")
        return await self.page.screenshot(full_page=True)
    
    async def close(self) -> None:
        """Close the page/browser."""
        debug_print("Closing application")
        await self.page.close()
