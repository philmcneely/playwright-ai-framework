"""
Main application page object for The Internet test site.
Provides centralized access to all page objects.
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
