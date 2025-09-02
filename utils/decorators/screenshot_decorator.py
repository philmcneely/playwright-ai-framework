import functools
import os
from pathlib import Path
import allure
from datetime import datetime

def screenshot_on_failure(func):
    """
    Decorator that automatically captures a screenshot on test failure.
    Works with any test that has 'app', 'login_page', or 'page' fixture.
    
    By convention, any fixture named 'app' or ending with '_page' is assumed
    to be a page object that has a .page attribute
    
    Note: This decorator will automatically find page objects from the test's
    fixture arguments, so you don't need to add 'request' to every test.
    
    Usage:
        @screenshot_on_failure
        @pytest.mark.asyncio
        async def test_something(app):  # No need for 'request' parameter
            # ... test code ...
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Try to find request fixture if it was passed
        request = kwargs.get('request')
        
        # Find page object using the same scalable logic
        page = None
        page_source = None
        
        # Loop through all kwargs to find page objects
        for key, value in kwargs.items():
            try:
                # Check if this is the 'app' fixture with a page attribute
                if key == "app" and hasattr(value, "page"):
                    page = value.page
                    page_source = f"app fixture"
                    break
                
                # Check if this is a page object fixture (ends with '_page')
                elif key.endswith("_page") and hasattr(value, "page"):
                    page = value.page
                    page_source = f"{key} fixture"
                    break
                
                # Check if this is the raw Playwright 'page' fixture
                elif key == "page":
                    page = value
                    page_source = f"page fixture"
                    break
                    
            except Exception:
                continue
        
        try:
            # Run the actual test function
            return await func(*args, **kwargs)
        except Exception as exc:
            # Test failed - attempt to capture screenshot if enabled
            if os.getenv("AI_HEALING_ENABLED", "false").lower() == "true":
                #print("AI healing is enabled; skipping regular screenshot capture.") #broken, always takes screenshot
                pass
            elif page and os.getenv("SKIP_SCREENSHOTS", "0") != "1":
                try:
                    screenshot_dir = Path("test_artifacts/allure/screenshots")
                    screenshot_dir.mkdir(exist_ok=True)
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    
                    # Use function name or request nodeid if available
                    if request:
                        test_name = request.node.nodeid.replace("/", "_").replace("::", "_")
                    else:
                        test_name = func.__name__
                    
                    screenshot_path = screenshot_dir / f"{test_name}_{timestamp}.png"
                    
                    # Capture the screenshot
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    
                    # Attach screenshot to Allure report
                    allure.attach.file(
                        str(screenshot_path),
                        name="Screenshot on Failure",
                        attachment_type=allure.attachment_type.PNG
                    )
                    
                    print(f"Screenshot saved and attached to Allure: {screenshot_path}")
                    #print(f"Page object found via: {page_source}")
                    
                except Exception as screenshot_error:
                    print(f"Failed to capture screenshot: {screenshot_error}")
            
            elif not page:
                available_fixtures = list(kwargs.keys())
                print(f"No page object found for screenshot. Available fixtures: {available_fixtures}")
            
            # Re-raise the original test exception
            raise exc
    
    return wrapper
