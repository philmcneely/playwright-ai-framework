"""
Login page object for The Internet test site.
"""
from playwright.async_api import Page
from pages.base_page import BasePage
from config.settings import settings
from utils.debug import debug_print


class LoginPage(BasePage):
    """Page object for login functionality on The Internet test site."""
    
    def __init__(self, page: Page):
        super().__init__(page)
        self.url = f"{settings.BASE_URL}/login"
        
        # Locators
        self.username_input = page.locator("#username")
        self.password_input = page.locator("#password")
        self.login_button = page.locator("button[type='submit']")
        self.flash_message = page.locator("#flash")
        self.page_title = page.locator("h2")
        
        # Error message locators
        self.error_message = page.locator(".flash.error")
        self.success_message = page.locator(".flash.success")
    
    async def navigate(self) -> None:
        """Navigate to the login page."""
        debug_print(f"Navigating to login page: {self.url}")
        await self.navigate_to(self.url)
        await self.wait_for_load_state()
    
    async def login(self, username: str, password: str) -> None:
        """Perform login with provided credentials."""
        debug_print(f"Attempting login with username: {username}")
        
        await self.fill_text(self.username_input, username)
        await self.fill_text(self.password_input, password)
        await self.click_element(self.login_button)
        
        # Wait for page to respond (either success or error)
        await self.page.wait_for_load_state("networkidle")
    
    async def login_with_demo_user(self) -> None:
        """Login with the demo user credentials from settings."""
        demo_user = settings.DEMO_USER
        await self.login(demo_user["username"], demo_user["password"])
    
    async def login_with_admin_user(self) -> None:
        """Login with the admin user credentials from settings."""
        admin_user = settings.ADMIN_USER
        await self.login(admin_user["username"], admin_user["password"])
    
    async def get_flash_message(self) -> str:
        """Get the flash message text."""
        if await self.is_visible(self.flash_message):
            return await self.get_text(self.flash_message)
        return ""
    
    async def is_login_successful(self) -> bool:
        """Check if login was successful by looking for success indicators."""
        try:
            # Check if we're redirected to secure area
            await self.page.wait_for_url("**/secure", timeout=5000)
            return True
        except Exception:
            return False
    
    async def is_error_displayed(self) -> bool:
        """Check if login error is displayed."""
        return await self.is_visible(self.error_message)
    
    async def get_page_title(self) -> str:
        """Get the page title text."""
        return await self.get_text(self.page_title)
    
    async def clear_form(self) -> None:
        """Clear the login form fields."""
        debug_print("Clearing login form")
        await self.username_input.clear()
        await self.password_input.clear()
    
    async def is_username_field_visible(self) -> bool:
        """Check if username field is visible."""
        return await self.is_visible(self.username_input)
    
    async def is_password_field_visible(self) -> bool:
        """Check if password field is visible."""
        return await self.is_visible(self.password_input)
    
    async def is_login_button_visible(self) -> bool:
        """Check if login button is visible."""
        return await self.is_visible(self.login_button)
    
    async def get_username_value(self) -> str:
        """Get the current value in username field."""
        return await self.username_input.input_value()
    
    async def get_password_value(self) -> str:
        """Get the current value in password field."""
        return await self.password_input.input_value()
