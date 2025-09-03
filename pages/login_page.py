"""
===============================================================================
LoginPage Object for The Internet Test Site
===============================================================================
This module defines the LoginPage class, which provides locators and helper
methods for interacting with the login form and verifying login functionality
on The Internet test site using Playwright.

Features:
    ✓ Locators for username and password input fields
    ✓ Methods for entering credentials and submitting login form
    ✓ Error message handling and verification
    ✓ Usage of @property for clean locator access
    ✓ Async methods for Playwright compatibility

Usage Example:
    from pages.login_page import LoginPage
    
    @pytest.mark.asyncio
    async def test_valid_login(page):
        login_page = LoginPage(page)
        await login_page.navigate()
        await login_page.enter_username("tomsmith")
        await login_page.enter_password("SuperSecretPassword!")
        await login_page.click_login()
        
        # Verify successful login
        assert await login_page.is_login_successful()

Conventions:
    - All locators are defined as @property methods for clarity and reusability
    - All Playwright actions and queries are implemented as async methods
    - Error messages are handled with specific methods for different scenarios
    - Navigation methods are provided for direct page access

Author: PMAC
Site: The Internet (https://the-internet.herokuapp.com)
===============================================================================
"""
from .base_page import BasePage


class LoginPage(BasePage):
    def __init__(self, page):
        super().__init__(page)
        self.url = "https://the-internet.herokuapp.com/login"

    # =====================================
    # Navigation Methods
    # =====================================
    async def navigate(self):
        """Navigate directly to the login page."""
        await self.goto(self.url)

    async def load(self):
        """Load the login page (alias for navigate)."""
        await self.navigate()

    # =====================================
    # Username Field
    # =====================================
    @property
    def username_field(self):
        """Locator for the username input field."""
        return self.page.locator("#username")

    async def enter_username(self, username: str):
        """Enter username into the username field."""
        await self.username_field.fill(username)

    async def get_username_value(self) -> str:
        """Get the current value from the username field."""
        return await self.username_field.input_value()

    # =====================================
    # Password Field
    # =====================================
    @property
    def password_field(self):
        """Locator for the password input field."""
        return self.page.locator("#password")

    async def enter_password(self, password: str):
        """Enter password into the password field."""
        await self.password_field.fill(password)

    async def get_password_value(self) -> str:
        """Get the current value from the password field."""
        return await self.password_field.input_value()

    # =====================================
    # Login Button
    # =====================================
    @property
    def login_button(self):
        """Locator for the login submit button."""
        return self.page.locator("button[type='submit']")

    async def click_login(self):
        """Click the login button to submit the form."""
        await self.login_button.click()

    # =====================================
    # Convenience Methods
    # =====================================
    async def login_with_credentials(self, username: str, password: str):
        """Complete login flow with username and password."""
        await self.enter_username(username)
        await self.enter_password(password)
        await self.click_login()

    async def login(self, username: str, password: str):
        """Alias for login_with_credentials for backward compatibility."""
        await self.login_with_credentials(username, password)

    async def login_with_demo_user(self):
        """Login with the demo user credentials."""
        await self.login_with_credentials("tomsmith", "SuperSecretPassword!")

    async def get_flash_message(self) -> str:
        """Convenience method - returns flash message text (success or error)."""
        # Try success message first, then error message
        if await self.is_login_successful():
            return await self.get_success_message_text()
        elif await self.has_error_message():
            return await self.get_error_message_text()
        return ""

    async def clear_username(self):
        """Clear the username field."""
        await self.username_field.clear()

    async def clear_password(self):
        """Clear the password field."""
        await self.password_field.clear()

    async def enter_passwordx(self, password: str):
        """
        Intentionally broken method for AI healing testing.
        Uses incorrect locator to trigger healing mechanism.
        """
        # Incorrect locator - should be #password but using wrong selector
        wrong_password_field = self.page.locator("#passwordx")
        await wrong_password_field.fill(password)

    # =====================================
    # Success Verification
    # =====================================
    @property
    def success_message(self):
        """Locator for the success flash message."""
        return self.page.locator(".flash.success")

    async def is_login_successful(self) -> bool:
        """Check if login was successful by looking for success message."""
        return await self.success_message.is_visible()

    async def get_success_message_text(self) -> str:
        """Get the text of the success message."""
        if await self.success_message.is_visible():
            text = await self.success_message.text_content()
            return text.strip() if text else ""
        return ""

    # =====================================
    # Error Message Handling
    # =====================================
    @property
    def error_message(self):
        """Locator for the error flash message."""
        return self.page.locator(".flash.error")

    async def has_error_message(self) -> bool:
        """Check if an error message is displayed."""
        return await self.error_message.is_visible()

    async def get_error_message_text(self) -> str:
        """Get the text of the error message."""
        if await self.error_message.is_visible():
            text = await self.error_message.text_content()
            return text.strip() if text else ""
        return ""

    # =====================================
    # Page State Verification
    # =====================================
    async def is_on_login_page(self) -> bool:
        """Verify that we are on the login page."""
        current_url = await self.get_url()
        return "/login" in current_url

    async def get_page_heading(self) -> str:
        """Get the main heading text on the login page."""
        heading = self.page.locator("h2")
        if await heading.is_visible():
            return await heading.text_content() or ""
        return ""
