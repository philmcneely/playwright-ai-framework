"""
===============================================================================
BasePage Class
===============================================================================
This module defines the BasePage class, which serves as the foundation for all
page objects in The Internet test suite. It provides common functionality
and utilities that are shared across all page objects, promoting code reuse and
maintaining consistency.

Features:
    ✓ Common navigation and page interaction methods
    ✓ Shared utility functions for element waiting and verification
    ✓ Consistent error handling and logging across all page objects
    ✓ Base functionality for URL management and page state verification
    ✓ Foundation for implementing page object inheritance patterns

Usage Example:
    from pages.base_page import BasePage
    
    class LoginPage(BasePage):
        def __init__(self, page):
            super().__init__(page)
            self.url = "https://the-internet.herokuapp.com/login"
            
        async def load(self):
            await self.navigate_to(self.url)

Conventions:
    - All page objects should inherit from BasePage for consistency
    - Common functionality is implemented here to avoid code duplication
    - Page-specific logic should be implemented in individual page classes
    - All methods are async to maintain Playwright compatibility

Author: PMAC
Date: [2025-07-27]
===============================================================================
"""
from playwright.async_api import Page


class BasePage:
    def __init__(self, page: Page):
        self.page = page

    # =====================================
    # Basic Navigation Methods
    # =====================================
    async def goto(self, url: str):
        await self.page.goto(url)

    async def navigate_to(self, url: str):
        await self.page.goto(url)

    async def wait_for_load_state(self, state="load"):
        await self.page.wait_for_load_state(state)

    # =====================================
    # Page Information Methods
    # =====================================
    async def get_title(self) -> str:
        return await self.page.title()

    async def get_url(self) -> str:
        return self.page.url

    # =====================================
    # Element Interaction Methods
    # =====================================
    async def fill_text(self, locator, text: str):
        await locator.fill(text)

    async def click_element(self, locator):
        await locator.click()

    async def get_text(self, locator) -> str:
        text = await locator.text_content()
        return text or ""

    # =====================================
    # Element State Methods
    # =====================================
    async def is_visible(self, locator) -> bool:
        try:
            return await locator.is_visible()
        except Exception:
            return False

    async def wait_for_element(self, locator):
        await locator.wait_for(state="visible")
