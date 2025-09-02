"""
Network Interception & Mocking Utilities
========================================

This module provides network interception and API mocking capabilities for Playwright tests.
It allows you to mock API responses, simulate network conditions, and create predictable
test environments by controlling all network traffic.

Features:
    ✓ Mock API responses with custom JSON data
    ✓ Simulate network delays and failures
    ✓ Route-based request interception
    ✓ Request/response logging and debugging
    ✓ File-based mock data loading
    ✓ Dynamic response generation
    ✓ Network condition simulation (slow 3G, offline, etc.)

Usage:
    # Basic API mocking
    @pytest.mark.asyncio
    async def test_with_mocked_api(page, api_mocker):
        await api_mocker.mock_get("/api/users", {"users": [{"id": 1, "name": "John"}]})
        await page.goto("https://example.com")

    # File-based mocking
    await api_mocker.mock_from_file("/api/products", "mocks/products.json")

    # Network condition simulation
    await api_mocker.simulate_slow_network()

Dependencies:
    - playwright.async_api: Async Playwright Page and Route objects
    - pytest_asyncio: Async fixture support
    - json: JSON data handling
    - pathlib: File path operations

Author: Generated for Playwright network mocking
"""

import json
import asyncio
import pytest_asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Union, Callable
from playwright.async_api import Page, Route, Request


class NetworkMocker:
    """
    Network mocking and interception manager for Playwright tests.
    
    This class provides methods to intercept network requests and return
    mock responses, simulate network conditions, and log network activity.
    """
    
    def __init__(self, page: Page):
        """
        Initialize the NetworkMocker with a Playwright page.
        
        Args:
            page (Page): Playwright Page object to intercept requests for
        """
        self.page = page
        self.mocked_routes = {}
        self.request_log = []
        self.response_log = []
        self.default_delay = 0
        
    async def mock_get(self, url_pattern: str, response_data: Union[Dict, str], 
                      status: int = 200, headers: Optional[Dict] = None, delay: int = 0):
        """
        Mock GET requests to a specific URL pattern.
        
        Args:
            url_pattern (str): URL pattern to intercept (supports wildcards)
            response_data (Union[Dict, str]): JSON data or string to return
            status (int): HTTP status code (default: 200)
            headers (Optional[Dict]): Custom response headers
            delay (int): Response delay in milliseconds
            
        Example:
            await api_mocker.mock_get("/api/users/*", {"users": []})
            await api_mocker.mock_get("**/products.json", product_data, delay=500)
        """
        await self._mock_request("GET", url_pattern, response_data, status, headers, delay)
        
    async def mock_post(self, url_pattern: str, response_data: Union[Dict, str],
                       status: int = 201, headers: Optional[Dict] = None, delay: int = 0):
        """
        Mock POST requests to a specific URL pattern.
        
        Args:
            url_pattern (str): URL pattern to intercept
            response_data (Union[Dict, str]): Response data to return
            status (int): HTTP status code (default: 201)
            headers (Optional[Dict]): Custom response headers
            delay (int): Response delay in milliseconds
        """
        await self._mock_request("POST", url_pattern, response_data, status, headers, delay)
        
    async def mock_put(self, url_pattern: str, response_data: Union[Dict, str],
                      status: int = 200, headers: Optional[Dict] = None, delay: int = 0):
        """Mock PUT requests to a specific URL pattern."""
        await self._mock_request("PUT", url_pattern, response_data, status, headers, delay)
        
    async def mock_delete(self, url_pattern: str, response_data: Union[Dict, str] = None,
                         status: int = 204, headers: Optional[Dict] = None, delay: int = 0):
        """Mock DELETE requests to a specific URL pattern."""
        if response_data is None:
            response_data = ""
        await self._mock_request("DELETE", url_pattern, response_data, status, headers, delay)
        
    async def _mock_request(self, method: str, url_pattern: str, response_data: Union[Dict, str],
                           status: int, headers: Optional[Dict], delay: int):
        """
        Internal method to set up request mocking for any HTTP method.
        """
        if headers is None:
            headers = {"Content-Type": "application/json"}
            
        # Convert dict to JSON string if needed
        if isinstance(response_data, dict):
            response_body = json.dumps(response_data)
        else:
            response_body = str(response_data)
            
        async def handle_route(route: Route, request: Request):
            # Log the intercepted request
            self.request_log.append({
                "method": request.method,
                "url": request.url,
                "headers": dict(request.headers),
                "post_data": request.post_data
            })
            
            # Apply delay if specified
            if delay > 0:
                await asyncio.sleep(delay / 1000)  # Convert ms to seconds
                
            # Fulfill the request with mock data
            await route.fulfill(
                status=status,
                headers=headers,
                body=response_body
            )
            
            # Log the mock response
            self.response_log.append({
                "url": request.url,
                "status": status,
                "body": response_body[:200] + "..." if len(response_body) > 200 else response_body
            })
            
        # Register the route handler
        route_key = f"{method}:{url_pattern}"
        self.mocked_routes[route_key] = handle_route
        
        await self.page.route(url_pattern, handle_route)
        print(f"🔗 Mocked {method} {url_pattern} -> {status}")
        
    async def mock_from_file(self, url_pattern: str, file_path: str, 
                            status: int = 200, headers: Optional[Dict] = None, delay: int = 0):
        """
        Mock API response using data from a JSON file.
        
        Args:
            url_pattern (str): URL pattern to intercept
            file_path (str): Path to JSON file containing mock data
            status (int): HTTP status code
            headers (Optional[Dict]): Custom response headers
            delay (int): Response delay in milliseconds
            
        Example:
            await api_mocker.mock_from_file("/api/users", "test_data/users.json")
        """
        try:
            with open(file_path, 'r') as f:
                mock_data = json.load(f)
            await self.mock_get(url_pattern, mock_data, status, headers, delay)
            print(f"📁 Loaded mock data from {file_path}")
        except FileNotFoundError:
            print(f"❌ Mock file not found: {file_path}")
            raise
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in mock file {file_path}: {e}")
            raise
            
    async def mock_with_function(self, url_pattern: str, response_function: Callable,
                                method: str = "GET"):
        """
        Mock API response using a dynamic function.
        
        Args:
            url_pattern (str): URL pattern to intercept
            response_function (Callable): Function that returns response data
            method (str): HTTP method to mock
            
        Example:
            def dynamic_response(request):
                return {"timestamp": time.time(), "user_id": request.query_params.get("id")}
            
            await api_mocker.mock_with_function("/api/dynamic", dynamic_response)
        """
        async def handle_route(route: Route, request: Request):
            try:
                response_data = response_function(request)
                if isinstance(response_data, dict):
                    response_body = json.dumps(response_data)
                    headers = {"Content-Type": "application/json"}
                else:
                    response_body = str(response_data)
                    headers = {"Content-Type": "text/plain"}
                    
                await route.fulfill(
                    status=200,
                    headers=headers,
                    body=response_body
                )
                
                self.response_log.append({
                    "url": request.url,
                    "status": 200,
                    "body": response_body[:200] + "..." if len(response_body) > 200 else response_body
                })
                
            except Exception as e:
                print(f"❌ Error in dynamic response function: {e}")
                await route.fulfill(status=500, body=json.dumps({"error": str(e)}))
                
        await self.page.route(url_pattern, handle_route)
        print(f"🔧 Dynamic mock registered for {method} {url_pattern}")
        
    async def simulate_network_failure(self, url_pattern: str = "**/*"):
        """
        Simulate network failures for matching requests.
        
        Args:
            url_pattern (str): URL pattern to fail (default: all requests)
        """
        async def fail_route(route: Route, request: Request):
            print(f"💥 Simulating network failure for {request.url}")
            await route.abort("failed")
            
        await self.page.route(url_pattern, fail_route)
        print(f"💥 Network failure simulation enabled for {url_pattern}")
        
    async def simulate_slow_network(self, delay_ms: int = 3000, url_pattern: str = "**/*"):
        """
        Simulate slow network conditions.
        
        Args:
            delay_ms (int): Delay in milliseconds (default: 3000ms = 3s)
            url_pattern (str): URL pattern to slow down
        """
        self.default_delay = delay_ms
        
        async def slow_route(route: Route, request: Request):
            print(f"🐌 Simulating slow network ({delay_ms}ms) for {request.url}")
            await asyncio.sleep(delay_ms / 1000)
            await route.continue_()
            
        await self.page.route(url_pattern, slow_route)
        print(f"🐌 Slow network simulation enabled ({delay_ms}ms delay)")
        
    async def simulate_offline(self):
        """
        Simulate offline mode by failing all network requests.
        """
        await self.simulate_network_failure("**/*")
        print("📵 Offline mode simulation enabled")
        
    async def clear_mocks(self):
        """
        Clear all registered mocks and route handlers.
        """
        # Unroute all registered patterns
        for route_key in self.mocked_routes.keys():
            method, pattern = route_key.split(":", 1)
            await self.page.unroute(pattern)
            
        self.mocked_routes.clear()
        self.request_log.clear()
        self.response_log.clear()
        print("🧹 All mocks cleared")
        
    def get_request_log(self) -> list:
        """
        Get log of all intercepted requests.
        
        Returns:
            list: List of request dictionaries
        """
        return self.request_log.copy()
        
    def get_response_log(self) -> list:
        """
        Get log of all mock responses.
        
        Returns:
            list: List of response dictionaries
        """
        return self.response_log.copy()
        
    def print_network_activity(self):
        """
        Print summary of network activity for debugging.
        """
        print(f"\n📊 Network Activity Summary:")
        print(f"   Requests intercepted: {len(self.request_log)}")
        print(f"   Responses mocked: {len(self.response_log)}")
        print(f"   Active mocks: {len(self.mocked_routes)}")
        
        if self.request_log:
            print(f"\n📥 Recent Requests:")
            for req in self.request_log[-5:]:  # Show last 5
                print(f"   {req['method']} {req['url']}")
                
        if self.response_log:
            print(f"\n📤 Recent Responses:")
            for resp in self.response_log[-5:]:  # Show last 5
                print(f"   {resp['status']} {resp['url']}")


@pytest_asyncio.fixture
async def api_mocker(page: Page):
    """
    Pytest fixture that provides network mocking capabilities.
    
    This fixture creates a NetworkMocker instance tied to the current page
    and automatically cleans up mocks after each test.
    
    Args:
        page (Page): Playwright Page object from the page fixture
        
    Yields:
        NetworkMocker: Configured network mocker instance
        
    Example:
        @pytest.mark.asyncio
        async def test_api_integration(page, api_mocker):
            # Mock the API response
            await api_mocker.mock_get("/api/users", {"users": [{"id": 1, "name": "John"}]})
            
            # Navigate to page that calls the API
            await page.goto("https://example.com")
            
            # Verify the page behaves correctly with mocked data
            assert await page.locator(".user-name").text_content() == "John"
    """
    mocker = NetworkMocker(page)
    
    yield mocker
    
    # Cleanup after test
    await mocker.clear_mocks()


def create_mock_data_file(file_path: str, data: Dict[str, Any]):
    """
    Utility function to create mock data files for testing.
    
    Args:
        file_path (str): Path where the mock file should be created
        data (Dict[str, Any]): Data to write to the file
        
    Example:
        create_mock_data_file("test_data/users.json", {
            "users": [
                {"id": 1, "name": "John Doe", "email": "john@example.com"},
                {"id": 2, "name": "Jane Smith", "email": "jane@example.com"}
            ]
        })
    """
    # Create directory if it doesn't exist
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)
        
    print(f"📁 Mock data file created: {file_path}")


# Common mock data templates
MOCK_TEMPLATES = {
    "users": {
        "users": [
            {"id": 1, "name": "John Doe", "email": "john@example.com", "active": True},
            {"id": 2, "name": "Jane Smith", "email": "jane@example.com", "active": True},
            {"id": 3, "name": "Bob Johnson", "email": "bob@example.com", "active": False}
        ]
    },
    "products": {
        "products": [
            {"id": 1, "name": "Laptop", "price": 999.99, "category": "Electronics"},
            {"id": 2, "name": "Coffee Mug", "price": 12.99, "category": "Kitchen"},
            {"id": 3, "name": "Book", "price": 24.99, "category": "Education"}
        ]
    },
    "empty_list": {"data": [], "total": 0},
    "error": {"error": "Something went wrong", "code": 500},
    "loading": {"status": "loading", "message": "Please wait..."}
}


def get_mock_template(template_name: str) -> Dict[str, Any]:
    """
    Get a predefined mock data template.
    
    Args:
        template_name (str): Name of the template (users, products, empty_list, error, loading)
        
    Returns:
        Dict[str, Any]: Mock data template
        
    Example:
        user_data = get_mock_template("users")
        await api_mocker.mock_get("/api/users", user_data)
    """
    return MOCK_TEMPLATES.get(template_name, {}).copy()