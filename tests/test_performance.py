"""
Performance monitoring tests for The Internet test site.
Built-in performance tracking and measurement capabilities.
"""
import pytest
import time
from pages.app import App
from utils.debug import debug_print


class TestPerformance:
    """Performance monitoring test suite for timing and metrics."""
    
    @pytest.mark.performance
    async def test_login_performance(self, page):
        """Monitor login performance metrics and timing."""
        debug_print("Starting login performance test")
        
        app = App(page)
        
        # Measure navigation time
        start_time = time.time()
        await app.login.navigate()
        navigation_time = time.time() - start_time
        
        # Measure login action time
        start_time = time.time()
        await app.login.login_with_demo_user()
        login_time = time.time() - start_time
        
        # Verify performance thresholds
        assert navigation_time < 5.0, (
            f"Navigation took too long: {navigation_time}s"
        )
        assert login_time < 3.0, f"Login took too long: {login_time}s"
        
        debug_print(f"Navigation time: {navigation_time:.2f}s")
        debug_print(f"Login time: {login_time:.2f}s")
        debug_print("Login performance test completed")
    
    @pytest.mark.performance
    async def test_page_load_performance(self, page):
        """Monitor page load times for different pages."""
        debug_print("Starting page load performance test")
        
        app = App(page)
        
        # Test home page load time
        start_time = time.time()
        await app.navigate_to_home()
        await page.wait_for_load_state("networkidle")
        home_load_time = time.time() - start_time
        
        # Test login page load time
        start_time = time.time()
        await app.login.navigate()
        await page.wait_for_load_state("networkidle")
        login_load_time = time.time() - start_time
        
        # Verify performance thresholds
        assert home_load_time < 5.0, (
            f"Home page load too slow: {home_load_time}s"
        )
        assert login_load_time < 5.0, (
            f"Login page load too slow: {login_load_time}s"
        )
        
        debug_print(f"Home page load time: {home_load_time:.2f}s")
        debug_print(f"Login page load time: {login_load_time:.2f}s")
        debug_print("Page load performance test completed")
    
    @pytest.mark.performance
    async def test_form_interaction_performance(self, page):
        """Monitor performance of form interactions and submissions."""
        debug_print("Starting form interaction performance test")
        
        app = App(page)
        await app.login.navigate()
        
        # Measure form filling time
        start_time = time.time()
        await app.login.fill_text(app.login.username_input, "tomsmith")
        password_field = app.login.password_input
        await app.login.fill_text(password_field, "SuperSecretPassword!")
        form_fill_time = time.time() - start_time
        
        # Measure form submission time
        start_time = time.time()
        await app.login.click_element(app.login.login_button)
        await page.wait_for_load_state("networkidle")
        submission_time = time.time() - start_time
        
        # Verify performance thresholds
        assert form_fill_time < 2.0, (
            f"Form filling too slow: {form_fill_time}s"
        )
        assert submission_time < 3.0, (
            f"Form submission too slow: {submission_time}s"
        )
        
        debug_print(f"Form filling time: {form_fill_time:.2f}s")
        debug_print(f"Form submission time: {submission_time:.2f}s")
        debug_print("Form interaction performance test completed")
    
    @pytest.mark.performance
    async def test_element_visibility_performance(self, page):
        """Monitor performance of element visibility checks."""
        debug_print("Starting element visibility performance test")
        
        app = App(page)
        await app.login.navigate()
        
        # Measure element visibility check times
        start_time = time.time()
        await app.login.wait_for_element(app.login.username_input)
        username_wait_time = time.time() - start_time
        
        start_time = time.time()
        await app.login.wait_for_element(app.login.password_input)
        password_wait_time = time.time() - start_time
        
        start_time = time.time()
        await app.login.wait_for_element(app.login.login_button)
        button_wait_time = time.time() - start_time
        
        # Verify performance thresholds
        assert username_wait_time < 1.0, (
            f"Username field wait too slow: {username_wait_time}s"
        )
        assert password_wait_time < 1.0, (
            f"Password field wait too slow: {password_wait_time}s"
        )
        assert button_wait_time < 1.0, (
            f"Button wait too slow: {button_wait_time}s"
        )
        
        debug_print(f"Username field wait time: {username_wait_time:.2f}s")
        debug_print(f"Password field wait time: {password_wait_time:.2f}s")
        debug_print(f"Button wait time: {button_wait_time:.2f}s")
        debug_print("Element visibility performance test completed")
    
    @pytest.mark.performance
    async def test_network_performance(self, page):
        """Monitor network-related performance metrics."""
        debug_print("Starting network performance test")
        
        app = App(page)
        
        # Enable network monitoring
        await page.route("**/*", lambda route: route.continue_())
        
        # Measure network-dependent operations
        start_time = time.time()
        await app.login.navigate()
        await page.wait_for_load_state("domcontentloaded")
        dom_load_time = time.time() - start_time
        
        start_time = time.time()
        await page.wait_for_load_state("networkidle")
        network_idle_time = time.time() - start_time
        
        # Verify network performance thresholds
        assert dom_load_time < 3.0, f"DOM load too slow: {dom_load_time}s"
        assert network_idle_time < 2.0, (
            f"Network idle too slow: {network_idle_time}s"
        )
        
        debug_print(f"DOM load time: {dom_load_time:.2f}s")
        debug_print(f"Network idle time: {network_idle_time:.2f}s")
        debug_print("Network performance test completed")
    
    @pytest.mark.performance
    async def test_full_workflow_performance(self, page):
        """Monitor performance of complete login-logout workflow."""
        debug_print("Starting full workflow performance test")
        
        app = App(page)
        
        # Measure complete workflow time
        start_time = time.time()
        
        # Navigate to login
        await app.login.navigate()
        
        # Perform login
        await app.login.login_with_demo_user()
        
        # Verify secure page
        assert await app.secure.is_on_secure_page()
        
        # Perform logout
        await app.secure.logout()
        
        # Verify back on login page
        assert await app.login.is_username_field_visible()
        
        total_workflow_time = time.time() - start_time
        
        # Verify total workflow performance
        assert total_workflow_time < 10.0, (
            f"Full workflow too slow: {total_workflow_time}s"
        )
        
        debug_print(f"Full workflow time: {total_workflow_time:.2f}s")
        debug_print("Full workflow performance test completed")
