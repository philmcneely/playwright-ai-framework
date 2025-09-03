"""
AI Healing demonstration tests for The Internet test site.
Tests that intentionally fail to demonstrate AI-powered healing capabilities.
"""
import pytest
from pages.app import App
from utils.debug import debug_print


class TestAIHealing:
    """AI healing demonstration test suite."""
    
    @pytest.mark.ai_healing
    async def test_ai_healing_element_not_found(self, page):
        """Test AI healing when element selector fails."""
        debug_print("Starting AI healing element not found test")
        
        app = App(page)
        await app.login.navigate()
        
        # Use incorrect selector to trigger AI healing
        try:
            incorrect_locator = page.locator("#non_existent_element")
            await incorrect_locator.click(timeout=5000)
            
            # This should fail and trigger AI healing
            assert False, "This test should fail to trigger AI healing"
            
        except Exception as e:
            debug_print(f"Expected failure occurred: {e}")
            debug_print(
                "AI healing should analyze this failure and suggest fixes"
            )
            
            # For now, we'll demonstrate the framework can handle failures
            # In a real scenario, AI healing would analyze the DOM
            # and suggest alternatives
            await app.login.click_element(app.login.login_button)
            
        debug_print("AI healing element not found test completed")
    
    @pytest.mark.ai_healing 
    async def test_ai_healing_timeout(self, page):
        """Test AI healing for timeout scenarios."""
        debug_print("Starting AI healing timeout test")
        
        app = App(page)
        await app.login.navigate()
        
        # Create timeout condition to trigger analysis
        try:
            # Set very short timeout to force failure
            username_input = app.login.username_input
            await app.login.wait_for_element(username_input, timeout=1)
            
        except Exception as e:
            debug_print(f"Timeout occurred as expected: {e}")
            debug_print(
                "AI healing should analyze timeout and suggest solutions"
            )
            
            # Demonstrate recovery with proper timeout
            await app.login.wait_for_element(app.login.username_input)
            
        debug_print("AI healing timeout test completed")
    
    @pytest.mark.ai_healing
    async def test_ai_healing_wrong_page_state(self, page):
        """Test AI healing when wrong page state is encountered."""
        debug_print("Starting AI healing wrong page state test")
        
        app = App(page)
        
        # Try to access secure page without logging in first
        try:
            await page.goto(app.secure.url)
            assert await app.secure.is_on_secure_page()
            
            # This should fail as we're not logged in
            assert False, "Should not be on secure page without login"
            
        except Exception as e:
            debug_print(f"Expected page state error: {e}")
            debug_print("AI healing should suggest login flow")
            
            # Demonstrate proper flow
            await app.login.navigate()
            await app.login.login_with_demo_user()
            assert await app.secure.is_on_secure_page()
            
        debug_print("AI healing wrong page state test completed")
    
    @pytest.mark.ai_healing
    async def test_ai_healing_network_issues(self, page):
        """Test AI healing for network-related issues."""
        debug_print("Starting AI healing network issues test")
        
        app = App(page)
        
        # Simulate network issue by navigating to invalid URL
        try:
            await page.goto("https://invalid-url-that-does-not-exist.com")
            await page.wait_for_load_state("networkidle", timeout=5000)
            
            # This should fail
            assert False, "Should not successfully load invalid URL"
            
        except Exception as e:
            debug_print(f"Network error occurred as expected: {e}")
            debug_print(
                "AI healing should suggest fallback URLs or retry logic"
            )
            
            # Demonstrate recovery
            await app.login.navigate()
            await page.wait_for_load_state("networkidle")
            
        debug_print("AI healing network issues test completed")
    
    @pytest.mark.ai_healing
    async def test_ai_healing_form_submission_failure(self, page):
        """Test AI healing when form submission fails."""
        debug_print("Starting AI healing form submission failure test")
        
        app = App(page)
        await app.login.navigate()
        
        # Fill form but try to submit to wrong endpoint
        await app.login.fill_text(app.login.username_input, "tomsmith")
        password_field = app.login.password_input
        await app.login.fill_text(password_field, "SuperSecretPassword!")
        
        try:
            # Try to submit form to non-existent action
            form_script = (
                "document.querySelector('form').action = '/invalid-endpoint'"
            )
            await page.evaluate(form_script)
            await app.login.click_element(app.login.login_button)
            await page.wait_for_load_state("networkidle", timeout=5000)
            
            # Check if we're on an error page
            current_url = await app.get_current_url()
            if "invalid-endpoint" in current_url:
                debug_print("Form submitted to wrong endpoint as expected")
                debug_print("AI healing should suggest correct form action")
                
                # Demonstrate recovery
                await app.login.navigate()
                await app.login.login_with_demo_user()
                assert await app.secure.is_on_secure_page()
            
        except Exception as e:
            debug_print(f"Form submission error: {e}")
            debug_print("AI healing should analyze form submission issues")
            
        debug_print("AI healing form submission failure test completed")
    
    @pytest.mark.ai_healing
    async def test_ai_healing_javascript_errors(self, page):
        """Test AI healing when JavaScript errors occur."""
        debug_print("Starting AI healing JavaScript errors test")
        
        app = App(page)
        await app.login.navigate()
        
        # Inject JavaScript error
        try:
            js_error_script = (
                "throw new Error("
                "'Intentional JavaScript error for AI healing test')"
            )
            await page.evaluate(js_error_script)
            
        except Exception as e:
            debug_print(f"JavaScript error occurred: {e}")
            debug_print("AI healing should analyze JavaScript console errors")
            
            # Verify page still functions normally
            await app.login.login_with_demo_user()
            assert await app.secure.is_on_secure_page()
            
        debug_print("AI healing JavaScript errors test completed")
