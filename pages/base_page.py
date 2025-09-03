"""
===============================================================================
BasePage Class for The Internet Test Site
===============================================================================
This module defines the BasePage class, which serves as the foundation for all
page objects in The Internet test site automation suite. It provides common
functionality and utilities that are shared across all page objects, promoting
code reuse and maintaining consistency.

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
        
        async def navigate(self):
            await self.navigate_to(self.url)

Conventions:
    - All page objects should inherit from BasePage for consistency
    - Common functionality is implemented here to avoid code duplication
    - Page-specific logic should be implemented in individual page classes
    - All methods are async to maintain Playwright compatibility

Dependencies:
    - playwright.async_api: Page and Locator objects
    - config.settings: Environment configuration
    - utils.debug: Debug logging utilities

Author: Playwright AI Test Framework
Site: The Internet (https://the-internet.herokuapp.com)
===============================================================================
"""
from abc import ABC
from typing import Literal
from playwright.async_api import Page, Locator, expect
from config.settings import settings
from utils.debug import debug_print


class BasePage(ABC):
    """Abstract base page class with common page functionality."""
    
    def __init__(self, page: Page):
        self.page = page
        self.timeout = settings.DEFAULT_TIMEOUT
    
    async def navigate_to(self, url: str) -> None:
        """Navigate to a specific URL."""
        debug_print(f"Navigating to: {url}")
        await self.page.goto(url, timeout=settings.NAVIGATION_TIMEOUT)
    
    async def wait_for_load_state(
        self,
        state: Literal["domcontentloaded", "load", "networkidle"] = "load"
    ) -> None:
        """Wait for page to reach a specific load state."""
        debug_print(f"Waiting for load state: {state}")
        await self.page.wait_for_load_state(state)
    
    async def get_title(self) -> str:
        """Get the page title."""
        return await self.page.title()
    
    async def get_url(self) -> str:
        """Get the current page URL."""
        return self.page.url
    
    async def wait_for_element(self, locator: Locator) -> None:
        """Wait for an element to be visible."""
        debug_print(f"Waiting for element: {locator}")
        await locator.wait_for(state="visible", timeout=self.timeout)
    
    async def click_element(self, locator: Locator) -> None:
        """Click an element with error handling."""
        debug_print(f"Clicking element: {locator}")
        await locator.wait_for(state="visible", timeout=self.timeout)
        await locator.click()
    
    async def fill_text(self, locator: Locator, text: str) -> None:
        """Fill text in an input field."""
        debug_print(f"Filling text '{text}' in: {locator}")
        await locator.wait_for(state="visible", timeout=self.timeout)
        await locator.fill(text)
    
    async def get_text(self, locator: Locator) -> str:
        """Get text content from an element."""
        await locator.wait_for(state="visible", timeout=self.timeout)
        text = await locator.text_content()
        return text or ""
    
    async def is_visible(self, locator: Locator) -> bool:
        """Check if an element is visible."""
        try:
            await locator.wait_for(state="visible", timeout=5000)
            return True
        except Exception:
            return False
    
    async def take_screenshot(self, name: str = "screenshot") -> bytes:
        """Take a screenshot of the current page."""
        debug_print(f"Taking screenshot: {name}")
        return await self.page.screenshot(full_page=True)
    
    async def expect_url_contains(self, text: str) -> None:
        """Assert that URL contains specific text."""
        await expect(self.page).to_have_url(f".*{text}.*")
    
    async def expect_title_contains(self, text: str) -> None:
        """Assert that title contains specific text."""
        await expect(self.page).to_have_title(f".*{text}.*")
    
    async def expect_element_visible(self, locator: Locator) -> None:
        """Assert that element is visible."""
        await expect(locator).to_be_visible()
    
    async def expect_element_text(self, locator: Locator, text: str) -> None:
        """Assert that element contains specific text."""
        await expect(locator).to_contain_text(text)
