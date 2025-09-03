"""
Visual regression tests for The Internet test site.
Screenshot comparison and visual testing capabilities.
"""
import pytest
from pages.app import App
from utils.debug import debug_print


class TestVisualRegression:
    """Visual regression test suite for screenshot comparison."""
    
    @pytest.mark.visual
    async def test_login_page_visual_regression(self, page, visual_regression):
        """Visual regression test for login page layout and elements."""
        debug_print("Starting login page visual regression test")
        
        app = App(page)
        await app.login.navigate()
        
        # Wait for page to fully load
        await app.login.wait_for_element(app.login.username_input)
        await app.login.wait_for_element(app.login.password_input)
        await app.login.wait_for_element(app.login.login_button)
        
        # Take full page screenshot for comparison
        await visual_regression("login_page", full_page=True, tolerance=0.02)
        
        debug_print("Login page visual regression test completed")
    
    @pytest.mark.visual
    async def test_secure_area_visual_regression(
        self, page, visual_regression
    ):
        """Visual regression test for secure area after successful login."""
        debug_print("Starting secure area visual regression test")
        
        app = App(page)
        
        # Login to access secure area
        await app.login.navigate()
        await app.login.login_with_demo_user()
        
        # Wait for secure page elements to load
        await app.secure.wait_for_element(app.secure.logout_button)
        await app.secure.wait_for_element(app.secure.page_title)
        
        # Take screenshot of secure area
        await visual_regression("secure_area", full_page=True, tolerance=0.02)
        
        debug_print("Secure area visual regression test completed")
    
    @pytest.mark.visual
    async def test_login_form_elements_visual(self, page, visual_regression):
        """Visual regression test for login form elements specifically."""
        debug_print("Starting login form elements visual test")
        
        app = App(page)
        await app.login.navigate()
        
        # Wait for form elements
        await app.login.wait_for_element(app.login.username_input)
        await app.login.wait_for_element(app.login.password_input)
        await app.login.wait_for_element(app.login.login_button)
        
        # Take screenshot of just the form area
        await visual_regression(
            "login_form",
            selector="form",
            full_page=False,
            tolerance=0.01
        )
        
        debug_print("Login form elements visual test completed")
    
    @pytest.mark.visual
    async def test_error_message_visual(self, page, visual_regression):
        """Visual regression test for error message display."""
        debug_print("Starting error message visual regression test")
        
        app = App(page)
        await app.login.navigate()
        
        # Trigger error message by submitting invalid credentials
        await app.login.login("invalid_user", "invalid_password")
        
        # Wait for error message to appear
        await app.login.wait_for_element(app.login.flash_message)
        
        # Take screenshot with error message visible
        await visual_regression(
            "login_error_message",
            full_page=True,
            tolerance=0.02
        )
        
        debug_print("Error message visual regression test completed")
    
    @pytest.mark.visual
    async def test_responsive_layout_visual(self, page, visual_regression):
        """Visual regression test for responsive layout at different sizes."""
        debug_print("Starting responsive layout visual test")
        
        app = App(page)
        
        # Test desktop size
        await page.set_viewport_size({"width": 1920, "height": 1080})
        await app.login.navigate()
        await app.login.wait_for_element(app.login.username_input)
        await visual_regression("login_desktop", tolerance=0.02)
        
        # Test tablet size
        await page.set_viewport_size({"width": 768, "height": 1024})
        await page.reload()
        await app.login.wait_for_element(app.login.username_input)
        await visual_regression("login_tablet", tolerance=0.02)
        
        # Test mobile size
        await page.set_viewport_size({"width": 375, "height": 667})
        await page.reload()
        await app.login.wait_for_element(app.login.username_input)
        await visual_regression("login_mobile", tolerance=0.03)
        
        debug_print("Responsive layout visual test completed")
    
    @pytest.mark.visual
    async def test_browser_specific_visual(self, page, visual_regression):
        """Visual regression test for browser-specific rendering."""
        debug_print("Starting browser-specific visual test")
        
        app = App(page)
        await app.login.navigate()
        
        # Wait for all elements to load
        await app.login.wait_for_element(app.login.username_input)
        await app.login.wait_for_element(app.login.password_input)
        await app.login.wait_for_element(app.login.login_button)
        
        # Get browser name for screenshot naming
        browser_name = page.context.browser.browser_type.name
        screenshot_name = f"login_page_{browser_name}"
        
        await visual_regression(screenshot_name, tolerance=0.02)
        
        debug_print(f"Browser-specific visual test completed for {browser_name}")
