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

Conventions:
    - All locators are defined as @property methods for clarity and reusability
    - All Playwright actions and queries are implemented as async methods
    - Page state verification methods for robust test assertions
    - Clear separation between actions and verifications

Author: PMAC
Site: The Internet (https://the-internet.herokuapp.com)
===============================================================================
"""
from .base_page import BasePage


class SecurePage(BasePage):
    def __init__(self, page):
        super().__init__(page)
        self.url = "https://the-internet.herokuapp.com/secure"

    # =====================================
    # Navigation Methods
    # =====================================
    async def navigate(self):
        """Navigate directly to the secure page (requires authentication)."""
        await self.goto(self.url)

    # =====================================
    # Page Heading
    # =====================================
    @property
    def page_heading(self):
        """Locator for the secure area page heading."""
        return self.page.locator("h2")

    async def get_page_heading_text(self) -> str:
        """Get the text of the page heading."""
        if await self.page_heading.is_visible():
            return await self.page_heading.text_content() or ""
        return ""

    # =====================================
    # Flash Messages
    # =====================================
    @property
    def flash_message(self):
        """Locator for flash messages (success/error)."""
        return self.page.locator("#flash")

    @property
    def success_message(self):
        """Locator for success flash message."""
        return self.page.locator(".flash.success")

    async def get_flash_message_text(self) -> str:
        """Get the text of the flash message."""
        if await self.flash_message.is_visible():
            text = await self.flash_message.text_content()
            return text.strip() if text else ""
        return ""

    async def has_success_message(self) -> bool:
        """Check if a success flash message is displayed."""
        return await self.success_message.is_visible()

    # =====================================
    # Convenience Methods (Backward Compatibility)
    # =====================================
    async def get_flash_message(self) -> str:
        """Convenience method - alias for get_flash_message_text()."""
        return await self.get_flash_message_text()

    # =====================================
    # Logout Functionality
    # =====================================
    @property
    def logout_link(self):
        """Locator for the logout link."""
        return self.page.locator("a[href='/logout']")

    async def logout(self):
        """Click the logout link to end the session."""
        await self.logout_link.click()

    async def is_logout_link_visible(self) -> bool:
        """Check if the logout link is visible on the page."""
        return await self.logout_link.is_visible()

    # =====================================
    # Page State Verification
    # =====================================
    async def is_on_secure_page(self) -> bool:
        """Verify that we are on the secure area page."""
        current_url = await self.get_url()
        return "/secure" in current_url

    async def is_authenticated(self) -> bool:
        """
        Verify that the user is authenticated by checking for secure page elements.
        This checks for both the correct URL and the presence of the logout link.
        """
        is_on_secure = await self.is_on_secure_page()
        has_logout = await self.is_logout_link_visible()
        return is_on_secure and has_logout

    # =====================================
    # Content Verification
    # =====================================
    async def get_page_content(self) -> str:
        """Get the main content text of the secure page."""
        content = self.page.locator(".subheader")
        if await content.is_visible():
            return await content.text_content() or ""
        return ""
