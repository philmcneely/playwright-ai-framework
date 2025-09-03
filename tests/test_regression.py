"""
Regression tests for The Internet test site.
Comprehensive test coverage for various functionality scenarios.
"""
import pytest
from pages.app import App
from test_data.test_data import TEST_URLS, VALID_USERS
from utils.debug import debug_print


class TestRegression:
    """Comprehensive regression test suite for The Internet functionality."""
    
    @pytest.mark.regression
    async def test_form_authentication_complete_flow(self, page):
        """Test complete form authentication flow with validation."""
        debug_print("Starting complete form authentication regression test")
        
        app = App(page)
        
        # Navigate to login page
        await app.login.navigate()
        
        # Test form field validation
        await app.login.fill_text(app.login.username_input, "")
        await app.login.fill_text(app.login.password_input, "")
        await app.login.click_element(app.login.login_button)
        
        # Verify still on login page
        assert await app.login.is_username_field_visible()
        
        # Test valid login
        await app.login.login_with_demo_user()
        
        # Verify successful navigation to secure area
        assert await app.secure.is_on_secure_page()
        assert await app.secure.is_logout_button_visible()
        
        # Test logout
        await app.secure.logout()
        
        # Verify back on login page
        assert await app.login.is_username_field_visible()
        
        debug_print(
            "Form authentication regression test completed successfully"
        )
    
    @pytest.mark.regression
    async def test_invalid_credentials_scenarios(self, page):
        """Test various invalid credential scenarios."""
        debug_print("Starting invalid credentials regression test")
        
        app = App(page)
        await app.login.navigate()
        
        # Test invalid username
        demo_password = VALID_USERS["demo_user"]["password"]
        await app.login.login("invalid_user", demo_password)
        error_message = await app.login.get_flash_message()
        assert "username is invalid" in error_message.lower()
        
        # Test invalid password
        await app.login.navigate()  # Refresh page
        demo_username = VALID_USERS["demo_user"]["username"]
        await app.login.login(demo_username, "invalid_password")
        error_message = await app.login.get_flash_message()
        assert "password is invalid" in error_message.lower()
        
        # Test both invalid
        await app.login.navigate()  # Refresh page
        await app.login.login("invalid_user", "invalid_password")
        error_message = await app.login.get_flash_message()
        assert "username is invalid" in error_message.lower()
        
        debug_print(
            "Invalid credentials regression test completed successfully"
        )
    
    @pytest.mark.regression
    async def test_page_elements_visibility(self, page):
        """Test visibility of all page elements across different pages."""
        debug_print("Starting page elements visibility test")
        
        app = App(page)
        
        # Test login page elements
        await app.login.navigate()
        assert await app.login.is_username_field_visible()
        assert await app.login.is_password_field_visible()
        assert await app.login.is_login_button_visible()
        
        page_title = await app.login.get_page_title()
        assert "Login Page" in page_title
        
        # Login and test secure page elements
        await app.login.login_with_demo_user()
        
        assert await app.secure.is_logout_button_visible()
        secure_title = await app.secure.get_page_title()
        assert "Secure Area" in secure_title
        
        debug_print("Page elements visibility test completed successfully")
    
    @pytest.mark.regression
    async def test_navigation_flow(self, page):
        """Test navigation between different pages."""
        debug_print("Starting navigation flow test")
        
        app = App(page)
        
        # Start at home page
        await app.navigate_to_home()
        current_url = await app.get_current_url()
        assert TEST_URLS["base"] in current_url
        
        # Navigate to login page
        await app.login.navigate()
        current_url = await app.get_current_url()
        assert "/login" in current_url
        
        # Login and verify secure page
        await app.login.login_with_demo_user()
        current_url = await app.get_current_url()
        assert "/secure" in current_url
        
        # Logout and verify return to login
        await app.secure.logout()
        current_url = await app.get_current_url()
        assert "/login" in current_url
        
        debug_print("Navigation flow test completed successfully")
    
    @pytest.mark.regression
    async def test_error_recovery(self, page):
        """Test error recovery scenarios."""
        debug_print("Starting error recovery test")
        
        app = App(page)
        
        # Test recovery from failed login
        await app.login.navigate()
        await app.login.login("invalid", "invalid")
        
        # Verify error message is displayed
        error_message = await app.login.get_flash_message()
        assert len(error_message) > 0
        
        # Test successful login after failed attempt
        await app.login.login_with_demo_user()
        assert await app.secure.is_on_secure_page()
        
        debug_print("Error recovery test completed successfully")
    
    @pytest.mark.regression
    async def test_session_management(self, page):
        """Test session management and persistence."""
        debug_print("Starting session management test")
        
        app = App(page)
        
        # Login successfully
        await app.login.navigate()
        await app.login.login_with_demo_user()
        assert await app.secure.is_on_secure_page()
        
        # Try to navigate directly to login page while logged in
        await app.login.navigate()
        # Should redirect to secure area or show logged in state
        
        # Logout to clean up session
        await app.page.goto(app.secure.url)  # Navigate to secure page directly
        await app.secure.logout()
        assert await app.login.is_username_field_visible()
        
        debug_print("Session management test completed successfully")
