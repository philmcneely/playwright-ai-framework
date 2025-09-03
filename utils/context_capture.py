"""
Unified context capture module for Playwright tests with AI healing capabilities.
Provides single screenshot method and comprehensive failure context capture.

This is not used yet.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import allure
from playwright.sync_api import Page
from config.artifact_paths import SCREENSHOT_DIR

DEFAULT_SCREENSHOT_DIR = SCREENSHOT_DIR

class ContextCapture:
    """Unified context capture with single screenshot method."""
    
    def __init__(self, screenshot_dir: str = None):
        self.screenshot_dir = DEFAULT_SCREENSHOT_DIR if screenshot_dir is None else Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    def capture_screenshot(self, page: Page, test_name: str = None, suffix: str = "") -> str:
        """
        Single unified screenshot capture method.
        This is the ONLY place where screenshots are created and stored.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        
        if test_name:
            filename = f"{timestamp}_{test_name}{suffix}.png"
        else:
            filename = f"{timestamp}_screenshot{suffix}.png"
        
        screenshot_path = self.screenshot_dir / filename
        
        try:
            # Capture screenshot
            page.screenshot(path=str(screenshot_path), full_page=True)
            
            # Attach to Allure if available
            try:
                with open(screenshot_path, "rb") as image_file:
                    allure.attach(
                        image_file.read(),
                        name=f"Screenshot_{test_name or 'capture'}{suffix}",
                        attachment_type=allure.attachment_type.PNG
                    )
            except Exception as e:
                print(f"Warning: Could not attach screenshot to Allure: {e}")
            
            return str(screenshot_path)
            
        except Exception as e:
            print(f"Error capturing screenshot: {e}")
            return ""
    
    def capture_dom_content(self, page: Page) -> Dict[str, Any]:
        """Capture comprehensive DOM content for AI analysis."""
        try:
            dom_content = {
                "url": page.url,
                "title": page.title(),
                "html": page.content(),
                "viewport": page.viewport_size,
                "user_agent": page.evaluate("navigator.userAgent"),
                "timestamp": datetime.now().isoformat()
            }
            
            # Get visible elements
            try:
                visible_elements = page.evaluate("""
                    () => {
                        const elements = [];
                        const walker = document.createTreeWalker(
                            document.body,
                            NodeFilter.SHOW_ELEMENT,
                            {
                                acceptNode: function(node) {
                                    const style = window.getComputedStyle(node);
                                    return style.display !== 'none' && 
                                           style.visibility !== 'hidden' && 
                                           style.opacity !== '0'
                                        ? NodeFilter.FILTER_ACCEPT 
                                        : NodeFilter.FILTER_REJECT;
                                }
                            }
                        );
                        
                        let node;
                        while (node = walker.nextNode()) {
                            const rect = node.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                elements.push({
                                    tag: node.tagName.toLowerCase(),
                                    id: node.id || '',
                                    className: node.className || '',
                                    text: node.textContent?.trim().substring(0, 100) || '',
                                    rect: {
                                        x: rect.x,
                                        y: rect.y,
                                        width: rect.width,
                                        height: rect.height
                                    }
                                });
                            }
                        }
                        return elements;
                    }
                """)
                dom_content["visible_elements"] = visible_elements
            except Exception as e:
                dom_content["visible_elements"] = []
                print(f"Warning: Could not capture visible elements: {e}")
            
            return dom_content
            
        except Exception as e:
            print(f"Error capturing DOM content: {e}")
            return {"error": str(e), "timestamp": datetime.now().isoformat()}
    
    def capture_failure_context(self, page: Page, test_name: str, error_message: str = "") -> Dict[str, Any]:
        """
        Comprehensive failure context capture using unified screenshot method.
        """
        context = {
            "test_name": test_name,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(),
            "screenshot_path": "",
            "dom_content": {},
            "page_objects": []
        }
        
        try:
            # Use unified screenshot method
            context["screenshot_path"] = self.capture_screenshot(page, test_name, "_failure")
            
            # Capture DOM content
            context["dom_content"] = self.capture_dom_content(page)
            
            # Find potential page objects
            context["page_objects"] = self.find_page_objects(page)
            
            # Attach context to Allure
            try:
                allure.attach(
                    json.dumps(context, indent=2, default=str),
                    name=f"Failure_Context_{test_name}",
                    attachment_type=allure.attachment_type.JSON
                )
            except Exception as e:
                print(f"Warning: Could not attach context to Allure: {e}")
            
        except Exception as e:
            context["capture_error"] = str(e)
            print(f"Error capturing failure context: {e}")
        
        return context
    
    def find_page_objects(self, page: Page) -> List[Dict[str, Any]]:
        """Find potential page objects and interactive elements."""
        try:
            page_objects = page.evaluate("""
                () => {
                    const objects = [];
                    
                    // Find forms
                    document.querySelectorAll('form').forEach((form, index) => {
                        objects.push({
                            type: 'form',
                            selector: form.id ? `#${form.id}` : `form:nth-of-type(${index + 1})`,
                            action: form.action || '',
                            method: form.method || 'get'
                        });
                    });
                    
                    // Find buttons
                    document.querySelectorAll('button, input[type="button"], input[type="submit"]').forEach(btn => {
                        const text = btn.textContent?.trim() || btn.value || '';
                        objects.push({
                            type: 'button',
                            selector: btn.id ? `#${btn.id}` : `button:contains("${text}")`,
                            text: text,
                            disabled: btn.disabled
                        });
                    });
                    
                    // Find input fields
                    document.querySelectorAll('input, textarea, select').forEach(input => {
                        objects.push({
                            type: 'input',
                            selector: input.id ? `#${input.id}` : input.name ? `[name="${input.name}"]` : input.type ? `input[type="${input.type}"]` : 'input',
                            inputType: input.type || 'text',
                            name: input.name || '',
                            placeholder: input.placeholder || '',
                            required: input.required
                        });
                    });
                    
                    // Find links
                    document.querySelectorAll('a[href]').forEach(link => {
                        const text = link.textContent?.trim() || '';
                        if (text) {
                            objects.push({
                                type: 'link',
                                selector: link.id ? `#${link.id}` : `a:contains("${text}")`,
                                href: link.href,
                                text: text
                            });
                        }
                    });
                    
                    return objects;
                }
            """)
            
            return page_objects
            
        except Exception as e:
            print(f"Error finding page objects: {e}")
            return []
    
    def ensure_ollama_ready(self, timeout: int = 30) -> bool:
        """Check if Ollama service is ready for AI healing."""
        try:
            import requests
            
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = requests.get("http://localhost:11434/api/tags", timeout=5)
                    if response.status_code == 200:
                        return True
                except requests.exceptions.RequestException:
                    pass
                time.sleep(1)
            
            return False
            
        except ImportError:
            print("Warning: requests library not available for Ollama check")
            return False
        except Exception as e:
            print(f"Error checking Ollama status: {e}")
            return False


# Global instance for easy access
_context_capture = ContextCapture()

# Public API functions
def capture_screenshot(page: Page, test_name: str = None, suffix: str = "") -> str:
    """Unified screenshot capture - single point of screenshot creation."""
    return _context_capture.capture_screenshot(page, test_name, suffix)

def capture_failure_context(page: Page, test_name: str, error_message: str = "") -> Dict[str, Any]:
    """Capture comprehensive failure context with screenshot."""
    return _context_capture.capture_failure_context(page, test_name, error_message)

def capture_dom_content(page: Page) -> Dict[str, Any]:
    """Capture DOM content for analysis."""
    return _context_capture.capture_dom_content(page)

def find_page_objects(page: Page) -> List[Dict[str, Any]]:
    """Find page objects and interactive elements."""
    return _context_capture.find_page_objects(page)

def ensure_ollama_ready(timeout: int = 30) -> bool:
    """Check if Ollama is ready for AI healing."""
    return _context_capture.ensure_ollama_ready(timeout)

def get_selector(page: Page, element_description: str) -> str:
    """Generate selector for element based on description."""
    try:
        # Simple selector generation - can be enhanced with AI
        page_objects = find_page_objects(page)
        
        # Look for matching elements
        for obj in page_objects:
            if element_description.lower() in obj.get('text', '').lower():
                return obj.get('selector', '')
            if element_description.lower() in obj.get('placeholder', '').lower():
                return obj.get('selector', '')
        
        # Fallback to text-based selector
        return f'text="{element_description}"'
        
    except Exception as e:
        print(f"Error generating selector: {e}")
        return f'text="{element_description}"'