"""
===============================================================================
SecurePage Object for The Internet Test Site
===============================================================================
This module defines the SecurePage class, which provides locators and helper
methods for interacting with the secure area page on The Internet test site.
This page is accessed after successful login and provides functionality for
logout and verification of authenticated state.

Features:
    ✓ Locators for secure area elements (page title, flash messages, logout)
    ✓ Methods for verifying successful login state
    ✓ Logout functionality and verification
    ✓ Flash message reading and validation
    ✓ URL-based page state verification

Usage Example:
    from pages.secure_page import SecurePage
    
    @pytest.mark.asyncio
    async def test_secure_area_access(page):
        secure_page = SecurePage(page)
        # After login...
        assert await secure_page.is_on_secure_page()
        flash_text = await secure_page.get_flash_message()
        assert "You logged into a secure area!" in flash_text
        await secure_page.logout()

Dependencies:
    - playwright.async_api: Async Page objects
    - pages.base_page: BasePage inheritance
    - config.settings: Environment configuration
    - utils.debug: Debug logging utilities

Author: Playwright AI Test Framework
Site: The Internet (https://the-internet.herokuapp.com)
===============================================================================
"""
from playwright.async_api import Page
from pages.base_page import BasePage
from config.settings import settings
from utils.debug import debug_print


class SecurePage(BasePage):
    """Page object for the secure area after successful login."""
    
    def __init__(self, page: Page):
        super().__init__(page)
        self.url = f"{settings.BASE_URL}/secure"
        
        # Locators
        self.page_title = page.locator("h2")
        self.flash_message = page.locator("#flash")
        self.logout_button = page.locator("a[href='/logout']")
        self.secure_area_text = page.locator(".subheader")
        
        # Success message locator
        self.success_message = page.locator(".flash.success")
    
    async def is_on_secure_page(self) -> bool:
        """Check if currently on the secure page."""
        try:
            current_url = await self.get_url()
            debug_print(f"Checking secure page - current URL: {current_url}")
            return "secure" in current_url
        except Exception as e:
            debug_print(f"Error checking secure page: {e}")
            return False
    
    async def get_page_title(self) -> str:
        """Get the secure page title."""
        return await self.get_text(self.page_title)
    
    async def get_flash_message(self) -> str:
        """Get the flash message text."""
        if await self.is_visible(self.flash_message):
            return await self.get_text(self.flash_message)
        return ""
    
    async def get_secure_area_text(self) -> str:
        """Get the secure area description text."""
        if await self.is_visible(self.secure_area_text):
            return await self.get_text(self.secure_area_text)
        return ""
    
    async def logout(self) -> None:
        """Click the logout button."""
        debug_print("Clicking logout button")
        await self.click_element(self.logout_button)
        await self.wait_for_load_state("networkidle")
    
    async def is_logout_button_visible(self) -> bool:
        """Check if logout button is visible."""
        return await self.is_visible(self.logout_button)
    
    async def is_success_message_displayed(self) -> bool:
        """Check if success message is displayed."""
        return await self.is_visible(self.success_message)
    
    async def wait_for_secure_page_load(self) -> None:
        """Wait for the secure page to fully load."""
        debug_print("Waiting for secure page to load")
        await self.wait_for_element(self.page_title)
        await self.wait_for_element(self.logout_button)
    
    async def verify_successful_login(self) -> bool:
        """Verify that login was successful and user is on secure page."""
        try:
            await self.wait_for_secure_page_load()
            is_on_page = await self.is_on_secure_page()
            has_logout = await self.is_logout_button_visible()
            return is_on_page and has_logout
        except Exception as e:
            debug_print(f"Failed to verify successful login: {e}")
            return False
