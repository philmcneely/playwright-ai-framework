"""
Secure page object for The Internet test site post-login area.
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
            await self.expect_url_contains("secure")
            return True
        except Exception:
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
