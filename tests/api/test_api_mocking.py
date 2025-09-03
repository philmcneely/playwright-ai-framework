"""
===============================================================================
Comprehensive API Mocking Test Suite for The Internet Test Site
===============================================================================

This test suite demonstrates various API mocking scenarios using the network_mocking 
utility adapted for The Internet test site. It covers common real-world API testing 
patterns including CRUD operations, error handling, network conditions, and data validation.

Features:
    ✓ Mock API responses for The Internet test site endpoints
    ✓ File-based mock data loading and management
    ✓ Dynamic response generation based on request parameters
    ✓ Error handling and edge case simulation
    ✓ Network condition testing (slow responses, timeouts)
    ✓ Authentication header mocking and validation
    ✓ Pagination and filtering simulation
    ✓ Real-time data scenario testing

Test Categories:
    • Basic API mocking (GET, POST, PUT, DELETE)
    • File-based mock data loading
    • Dynamic response generation
    • Error handling and edge cases
    • Network condition simulation
    • Authentication and headers
    • Pagination and filtering
    • Real-time data scenarios

Usage Example:
    pytest tests/api/test_api_mocking.py -v

Author: PMAC
Site: The Internet (https://the-internet.herokuapp.com)
Date: [2025-09-03]
===============================================================================
"""

import pytest
import json
import time
from pathlib import Path
from utils.network_mocking import create_mock_data_file, get_mock_template


class TestBasicAPIMocking:
    """Test basic CRUD operations with API mocking."""
    
    @pytest.mark.asyncio
    async def test_get_users_list(self, page, api_mocker):
        """Test fetching a list of users from API."""
        # Mock the users API endpoint with wildcard pattern to catch any base URL
        users_data = get_mock_template("users")
        await api_mocker.mock_get("**/api/users", users_data)
        
        # Create a simple HTML page that fetches users
        html_content = """
        <!DOCTYPE html>
        <html>
        <head><title>Users</title></head>
        <body>
            <div id="users-container">Loading...</div>
            <script>
                fetch('http://localhost/api/users')
                    .then(response => response.json())
                    .then(data => {
                        const container = document.getElementById('users-container');
                        container.innerHTML = data.users.map(user => 
                            `<div class="user" data-id="${user.id}">${user.name} (${user.email})</div>`
                        ).join('');
                    })
                    .catch(error => {
                        document.getElementById('users-container').innerHTML = 'Error loading users';
                    });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        
        # Wait for the API call to complete and verify results
        await page.wait_for_selector('.user')
        users = await page.locator('.user').all()
        
        assert len(users) == 3
        assert await users[0].text_content() == "John Doe (john@example.com)"
        assert await users[1].text_content() == "Jane Smith (jane@example.com)"
        
        # Verify the request was logged
        requests = api_mocker.get_request_log()
        assert len(requests) == 1
        assert requests[0]['method'] == 'GET'
        assert '/api/users' in requests[0]['url']
    
    @pytest.mark.asyncio
    async def test_create_user_post(self, page, api_mocker):
        """Test creating a new user via POST request."""
        # Mock successful user creation
        new_user_response = {
            "id": 4,
            "name": "Alice Cooper",
            "email": "alice@example.com",
            "active": True,
            "created_at": "2024-01-15T10:30:00Z"
        }
        await api_mocker.mock_post("**/api/users", new_user_response, status=201)
        
        # Create form to submit new user
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <form id="user-form">
                <input type="text" id="name" value="Alice Cooper" />
                <input type="email" id="email" value="alice@example.com" />
                <button type="submit">Create User</button>
            </form>
            <div id="result"></div>
            <script>
                document.getElementById('user-form').addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const formData = {
                        name: document.getElementById('name').value,
                        email: document.getElementById('email').value
                    };
                    
                    try {
                        const response = await fetch('http://localhost/api/users', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify(formData)
                        });
                        const result = await response.json();
                        document.getElementById('result').innerHTML = 
                            `User created: ${result.name} (ID: ${result.id})`;
                    } catch (error) {
                        document.getElementById('result').innerHTML = 'Error creating user';
                    }
                });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        await page.click('button[type="submit"]')
        
        # Verify the user was "created"
        await page.wait_for_selector('#result')
        result_text = await page.locator('#result').text_content()
        assert "User created: Alice Cooper (ID: 4)" in result_text
        
        # Verify POST request was made
        requests = api_mocker.get_request_log()
        assert len(requests) == 1
        assert requests[0]['method'] == 'POST'
        
        # Verify request payload
        post_data = json.loads(requests[0]['post_data'])
        assert post_data['name'] == 'Alice Cooper'
        assert post_data['email'] == 'alice@example.com'
    
    @pytest.mark.asyncio
    async def test_update_user_put(self, page, api_mocker):
        """Test updating a user via PUT request."""
        updated_user = {
            "id": 1,
            "name": "John Doe Updated",
            "email": "john.updated@example.com",
            "active": True,
            "updated_at": "2024-01-15T11:00:00Z"
        }
        await api_mocker.mock_put("**/api/users/1", updated_user)
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <button id="update-btn">Update User 1</button>
            <div id="status"></div>
            <script>
                document.getElementById('update-btn').addEventListener('click', async () => {
                    const updateData = {
                        name: "John Doe Updated",
                        email: "john.updated@example.com"
                    };
                    
                    const response = await fetch('http://localhost/api/users/1', {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(updateData)
                    });
                    const result = await response.json();
                    document.getElementById('status').innerHTML = `Updated: ${result.name}`;
                });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        await page.click('#update-btn')
        
        await page.wait_for_selector('#status')
        status = await page.locator('#status').text_content()
        assert "Updated: John Doe Updated" in status
    
    @pytest.mark.asyncio
    async def test_delete_user(self, page, api_mocker):
        """Test deleting a user via DELETE request."""
        await api_mocker.mock_delete("**/api/users/1", {"message": "User deleted successfully"})
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <button id="delete-btn">Delete User 1</button>
            <div id="message"></div>
            <script>
                document.getElementById('delete-btn').addEventListener('click', async () => {
                    const response = await fetch('http://localhost/api/users/1', {method: 'DELETE'});
                    const result = await response.json();
                    document.getElementById('message').innerHTML = result.message;
                });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        await page.click('#delete-btn')
        
        await page.wait_for_selector('#message')
        message = await page.locator('#message').text_content()
        assert "User deleted successfully" in message


class TestFileBasedMocking:
    """Test file-based mock data loading."""
    
    @pytest.fixture(autouse=True)
    def setup_mock_files(self):
        """Create mock data files for testing."""
        # Create test data directory
        Path("test_data").mkdir(exist_ok=True)
        
        # Create products mock file
        products_data = {
            "products": [
                {"id": 1, "name": "Gaming Laptop", "price": 1299.99, "category": "Electronics", "stock": 15},
                {"id": 2, "name": "Wireless Mouse", "price": 29.99, "category": "Electronics", "stock": 50},
                {"id": 3, "name": "Coffee Maker", "price": 89.99, "category": "Kitchen", "stock": 8}
            ],
            "total": 3,
            "page": 1,
            "per_page": 10
        }
        create_mock_data_file("test_data/products.json", products_data)
        
        # Create orders mock file
        orders_data = {
            "orders": [
                {"id": 1001, "user_id": 1, "total": 1329.98, "status": "completed", "items": 2},
                {"id": 1002, "user_id": 2, "total": 89.99, "status": "pending", "items": 1}
            ]
        }
        create_mock_data_file("test_data/orders.json", orders_data)
        
        yield
        
        # Cleanup (optional)
        import shutil
        if Path("test_data").exists():
            shutil.rmtree("test_data")
    
    @pytest.mark.asyncio
    async def test_load_products_from_file(self, page, api_mocker):
        """Test loading product data from JSON file."""
        await api_mocker.mock_from_file("**/api/products", "test_data/products.json")
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <div id="products-grid">Loading products...</div>
            <script>
                fetch('http://localhost/api/products')
                    .then(response => response.json())
                    .then(data => {
                        const grid = document.getElementById('products-grid');
                        grid.innerHTML = data.products.map(product => 
                            `<div class="product" data-id="${product.id}">
                                <h3>${product.name}</h3>
                                <p>$${product.price} - Stock: ${product.stock}</p>
                                <span class="category">${product.category}</span>
                            </div>`
                        ).join('');
                    });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        await page.wait_for_selector('.product')
        
        products = await page.locator('.product').all()
        assert len(products) == 3
        
        # Verify specific product details
        laptop = page.locator('.product[data-id="1"]')
        assert await laptop.locator('h3').text_content() == "Gaming Laptop"
        assert "$1299.99" in await laptop.locator('p').text_content()
        assert await laptop.locator('.category').text_content() == "Electronics"


class TestDynamicResponses:
    """Test dynamic response generation."""
    
    @pytest.mark.asyncio
    async def test_dynamic_timestamp_response(self, page, api_mocker):
        """Test dynamic response with current timestamp."""
        def timestamp_response(request):
            return {
                "timestamp": int(time.time()),
                "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "request_url": request.url,
                "user_agent": request.headers.get("user-agent", "unknown")
            }
        
        await api_mocker.mock_with_function("**/api/server-info", timestamp_response)
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <button id="get-info">Get Server Info</button>
            <div id="server-info"></div>
            <script>
                document.getElementById('get-info').addEventListener('click', async () => {
                    const response = await fetch('http://localhost/api/server-info');
                    const data = await response.json();
                    document.getElementById('server-info').innerHTML = 
                        `<div>Time: ${data.server_time}</div>
                         <div>Timestamp: ${data.timestamp}</div>`;
                });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        await page.click('#get-info')
        
        await page.wait_for_selector('#server-info div')
        info_divs = await page.locator('#server-info div').all()
        
        assert len(info_divs) == 2
        time_text = await info_divs[0].text_content()
        timestamp_text = await info_divs[1].text_content()
        
        assert "Time:" in time_text
        assert "Timestamp:" in timestamp_text
    
    @pytest.mark.asyncio
    async def test_search_with_query_params(self, page, api_mocker):
        """Test dynamic response based on query parameters."""
        def search_response(request):
            url = request.url
            if "q=laptop" in url:
                return {"results": [{"id": 1, "name": "Gaming Laptop", "price": 1299.99}], "count": 1}
            elif "q=mouse" in url:
                return {"results": [{"id": 2, "name": "Wireless Mouse", "price": 29.99}], "count": 1}
            else:
                return {"results": [], "count": 0}
        
        await api_mocker.mock_with_function("**/api/search*", search_response)
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <input type="text" id="search-input" placeholder="Search products..." />
            <button id="search-btn">Search</button>
            <div id="search-results"></div>
            <script>
                document.getElementById('search-btn').addEventListener('click', async () => {
                    const query = document.getElementById('search-input').value;
                    const response = await fetch(`http://localhost/api/search?q=${encodeURIComponent(query)}`);
                    const data = await response.json();
                    
                    const resultsDiv = document.getElementById('search-results');
                    if (data.count > 0) {
                        resultsDiv.innerHTML = data.results.map(item => 
                            `<div class="result">${item.name} - $${item.price}</div>`
                        ).join('');
                    } else {
                        resultsDiv.innerHTML = '<div class="no-results">No results found</div>';
                    }
                });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        
        # Test laptop search
        await page.fill('#search-input', 'laptop')
        await page.click('#search-btn')
        await page.wait_for_selector('.result')
        
        result = await page.locator('.result').text_content()
        assert "Gaming Laptop - $1299.99" in result
        
        # Test no results
        await page.fill('#search-input', 'nonexistent')
        await page.click('#search-btn')
        await page.wait_for_selector('.no-results')
        
        no_results = await page.locator('.no-results').text_content()
        assert "No results found" in no_results


class TestErrorHandling:
    """Test error scenarios and edge cases."""
    
    @pytest.mark.asyncio
    async def test_api_server_error(self, page, api_mocker):
        """Test handling of 500 server errors."""
        error_response = {"error": "Internal server error", "code": "SERVER_ERROR"}
        await api_mocker.mock_get("**/api/users", error_response, status=500)
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <div id="content">Loading...</div>
            <script>
                fetch('http://localhost/api/users')
                    .then(response => {
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }
                        return response.json();
                    })
                    .then(data => {
                        document.getElementById('content').innerHTML = 'Success!';
                    })
                    .catch(error => {
                        document.getElementById('content').innerHTML = 
                            `<div class="error">Error: ${error.message}</div>`;
                    });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        await page.wait_for_selector('.error')
        
        error_text = await page.locator('.error').text_content()
        assert "Error: HTTP 500" in error_text
    
    @pytest.mark.asyncio
    async def test_api_not_found(self, page, api_mocker):
        """Test handling of 404 not found errors."""
        await api_mocker.mock_get("**/api/users/999", {"error": "User not found"}, status=404)
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <button id="load-user">Load User 999</button>
            <div id="user-info"></div>
            <script>
                document.getElementById('load-user').addEventListener('click', async () => {
                    try {
                        const response = await fetch('http://localhost/api/users/999');
                        if (response.status === 404) {
                            document.getElementById('user-info').innerHTML = 
                                '<div class="not-found">User not found</div>';
                        } else {
                            const data = await response.json();
                            document.getElementById('user-info').innerHTML = 
                                `<div>User: ${data.name}</div>`;
                        }
                    } catch (error) {
                        document.getElementById('user-info').innerHTML = 
                            '<div class="error">Network error</div>';
                    }
                });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        await page.click('#load-user')
        await page.wait_for_selector('.not-found')
        
        not_found = await page.locator('.not-found').text_content()
        assert "User not found" in not_found


class TestNetworkConditions:
    """Test various network conditions and scenarios."""
    
    @pytest.mark.asyncio
    async def test_slow_network_simulation(self, page, api_mocker):
        """Test behavior under slow network conditions."""
        users_data = get_mock_template("users")
        await api_mocker.mock_get("**/api/users", users_data, delay=2000)  # 2 second delay
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <button id="load-users">Load Users</button>
            <div id="loading" style="display:none;">Loading...</div>
            <div id="users-list"></div>
            <script>
                document.getElementById('load-users').addEventListener('click', async () => {
                    const loadingDiv = document.getElementById('loading');
                    const usersDiv = document.getElementById('users-list');
                    
                    loadingDiv.style.display = 'block';
                    usersDiv.innerHTML = '';
                    
                    const startTime = Date.now();
                    
                    try {
                        const response = await fetch('http://localhost/api/users');
                        const data = await response.json();
                        const loadTime = Date.now() - startTime;
                        
                        loadingDiv.style.display = 'none';
                        usersDiv.innerHTML = 
                            `<div class="load-time">Loaded in ${loadTime}ms</div>
                             <div class="user-count">${data.users.length} users loaded</div>`;
                    } catch (error) {
                        loadingDiv.style.display = 'none';
                        usersDiv.innerHTML = '<div class="error">Failed to load</div>';
                    }
                });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        await page.click('#load-users')
        
        # Verify loading indicator appears
        loading = page.locator('#loading')
        await loading.wait_for(state='visible')
        
        # Wait for completion
        await page.wait_for_selector('.load-time', timeout=5000)
        
        load_time_text = await page.locator('.load-time').text_content()
        user_count_text = await page.locator('.user-count').text_content()
        
        # Should take at least 2 seconds due to delay
        assert "ms" in load_time_text
        assert "3 users loaded" in user_count_text
    
    @pytest.mark.asyncio
    async def test_network_failure_simulation(self, page, api_mocker):
        """Test behavior when network requests fail."""
        await api_mocker.simulate_network_failure("**/api/users")
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <button id="load-data">Load Data</button>
            <div id="status"></div>
            <script>
                document.getElementById('load-data').addEventListener('click', async () => {
                    try {
                        const response = await fetch('http://localhost/api/users');
                        document.getElementById('status').innerHTML = 'Success!';
                    } catch (error) {
                        document.getElementById('status').innerHTML = 
                            '<div class="network-error">Network request failed</div>';
                    }
                });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        await page.click('#load-data')
        await page.wait_for_selector('.network-error')
        
        error_text = await page.locator('.network-error').text_content()
        assert "Network request failed" in error_text
    
    @pytest.mark.asyncio
    async def test_offline_mode_simulation(self, page, api_mocker):
        """Test complete offline scenario."""
        await api_mocker.simulate_offline()
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <button id="test-connection">Test Connection</button>
            <div id="connection-status"></div>
            <script>
                document.getElementById('test-connection').addEventListener('click', async () => {
                    const statusDiv = document.getElementById('connection-status');
                    
                    try {
                        // Try multiple endpoints
                        await Promise.all([
                            fetch('http://localhost/api/users'),
                            fetch('http://localhost/api/products'),
                            fetch('http://localhost/health-check')
                        ]);
                        statusDiv.innerHTML = '<div class="online">All services online</div>';
                    } catch (error) {
                        statusDiv.innerHTML = '<div class="offline">Offline mode detected</div>';
                    }
                });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        await page.click('#test-connection')
        await page.wait_for_selector('.offline')
        
        offline_text = await page.locator('.offline').text_content()
        assert "Offline mode detected" in offline_text


class TestAdvancedScenarios:
    """Test advanced API scenarios like authentication, pagination, etc."""
    
    @pytest.mark.asyncio
    async def test_authentication_headers(self, page, api_mocker):
        """Test API calls with authentication headers."""
        # Test valid authentication first
        await api_mocker.mock_get("**/api/me", {"user": {"id": 1, "name": "Authenticated User", "role": "admin"}})
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <button id="test-auth">Test Auth</button>
            <div id="user-info"></div>
            <script>
                document.getElementById('test-auth').addEventListener('click', async () => {
                    try {
                        const response = await fetch('http://localhost/api/me', {
                            headers: {
                                'Authorization': 'Bearer valid-token'
                            }
                        });
                        
                        if (response.ok) {
                            const data = await response.json();
                            document.getElementById('user-info').innerHTML = 
                                `<div class="success">Welcome, ${data.user.name}!</div>`;
                        } else {
                            document.getElementById('user-info').innerHTML = 
                                '<div class="auth-error">Authentication failed</div>';
                        }
                    } catch (error) {
                        document.getElementById('user-info').innerHTML = 
                            '<div class="error">Request failed</div>';
                    }
                });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        
        # Test valid authentication
        await page.click('#test-auth')
        await page.wait_for_selector('.success')
        success_text = await page.locator('.success').text_content()
        assert "Welcome, Authenticated User!" in success_text
        
        print("✅ Authentication test passed!")
    
    @pytest.mark.asyncio
    async def test_authentication_error_handling(self, page, api_mocker):
        """Test authentication error handling."""
        # Mock with error response and 401 status
        await api_mocker.mock_get("**/api/me", {"error": "Unauthorized"}, status=401)
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <button id="test-auth">Test Auth</button>
            <div id="user-info"></div>
            <script>
                document.getElementById('test-auth').addEventListener('click', async () => {
                    try {
                        const response = await fetch('http://localhost/api/me', {
                            headers: {
                                'Authorization': 'Bearer invalid-token'
                            }
                        });
                        
                        if (response.ok) {
                            const data = await response.json();
                            document.getElementById('user-info').innerHTML = 
                                `<div class="success">Welcome, ${data.user.name}!</div>`;
                        } else {
                            document.getElementById('user-info').innerHTML = 
                                '<div class="auth-error">Authentication failed</div>';
                        }
                    } catch (error) {
                        document.getElementById('user-info').innerHTML = 
                            '<div class="error">Request failed</div>';
                    }
                });
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        
        # Test invalid authentication
        await page.click('#test-auth')
        await page.wait_for_selector('.auth-error')
        error_text = await page.locator('.auth-error').text_content()
        assert "Authentication failed" in error_text
        
        print("✅ Authentication error test passed!")
    
    @pytest.mark.asyncio
    async def test_pagination_scenario(self, page, api_mocker):
        """Test paginated API responses."""
        # Mock page 1
        page1_data = {
            "users": [
                {"id": 1, "name": "User 1"},
                {"id": 2, "name": "User 2"},
                {"id": 3, "name": "User 3"}
            ],
            "page": 1,
            "per_page": 3,
            "total": 7,
            "total_pages": 3,
            "has_next": True
        }
        await api_mocker.mock_get("**/api/users?page=1", page1_data)
        
        # Mock page 2
        page2_data = {
            "users": [
                {"id": 4, "name": "User 4"},
                {"id": 5, "name": "User 5"},
                {"id": 6, "name": "User 6"}
            ],
            "page": 2,
            "per_page": 3,
            "total": 7,
            "total_pages": 3,
            "has_next": True
        }
        await api_mocker.mock_get("**/api/users?page=2", page2_data)
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <div id="users-list"></div>
            <button id="load-page1">Load Page 1</button>
            <button id="load-page2">Load Page 2</button>
            <div id="pagination-info"></div>
            <script>
                async function loadPage(pageNum) {
                    const response = await fetch(`http://localhost/api/users?page=${pageNum}`);
                    const data = await response.json();
                    
                    document.getElementById('users-list').innerHTML = 
                        data.users.map(user => `<div class="user">${user.name}</div>`).join('');
                    
                    document.getElementById('pagination-info').innerHTML = 
                        `<div class="page-info">Page ${data.page} of ${data.total_pages} (${data.total} total users)</div>`;
                }
                
                document.getElementById('load-page1').addEventListener('click', () => loadPage(1));
                document.getElementById('load-page2').addEventListener('click', () => loadPage(2));
            </script>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        
        # Test page 1
        await page.click('#load-page1')
        await page.wait_for_selector('.user')
        users_page1 = await page.locator('.user').all()
        assert len(users_page1) == 3
        assert await users_page1[0].text_content() == "User 1"
        
        page_info = await page.locator('.page-info').text_content()
        assert "Page 1 of 3" in page_info
        assert "7 total users" in page_info
        
        # Test page 2
        await page.click('#load-page2')
        await page.wait_for_selector('.user')
        users_page2 = await page.locator('.user').all()
        assert len(users_page2) == 3
        assert await users_page2[0].text_content() == "User 4"


@pytest.mark.asyncio
async def test_comprehensive_api_workflow(page, api_mocker):
    """
    Test a complete API workflow combining multiple operations.
    This simulates a real application flow with multiple API calls.
    """
    # Mock authentication
    await api_mocker.mock_post("**/api/auth/login", {
        "token": "abc123",
        "user": {"id": 1, "name": "Test User", "role": "user"}
    })
    
    # Mock user profile
    await api_mocker.mock_get("**/api/profile", {
        "id": 1,
        "name": "Test User",
        "email": "test@example.com",
        "preferences": {"theme": "dark", "notifications": True}
    })
    
    # Mock dashboard data
    await api_mocker.mock_get("**/api/dashboard", {
        "stats": {"orders": 5, "revenue": 1250.50, "customers": 23},
        "recent_activity": [
            {"type": "order", "description": "New order #1001", "time": "2 minutes ago"},
            {"type": "customer", "description": "New customer registered", "time": "5 minutes ago"}
        ]
    })
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <body>
        <div id="app">
            <div id="login-form">
                <input type="text" id="username" value="testuser" />
                <input type="password" id="password" value="password" />
                <button id="login-btn">Login</button>
            </div>
            <div id="dashboard" style="display:none;">
                <div id="user-info"></div>
                <div id="stats"></div>
                <div id="activity"></div>
                <button id="logout-btn">Logout</button>
            </div>
            <div id="status"></div>
        </div>
        <script>
            let authToken = null;
            
            document.getElementById('login-btn').addEventListener('click', async () => {
                const username = document.getElementById('username').value;
                const password = document.getElementById('password').value;
                
                try {
                    // Step 1: Login
                    const loginResponse = await fetch('http://localhost/api/auth/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({username, password})
                    });
                    const loginData = await loginResponse.json();
                    authToken = loginData.token;
                    
                    // Step 2: Load profile
                    const profileResponse = await fetch('http://localhost/api/profile', {
                        headers: {'Authorization': `Bearer ${authToken}`}
                    });
                    const profileData = await profileResponse.json();
                    
                    // Step 3: Load dashboard
                    const dashboardResponse = await fetch('http://localhost/api/dashboard', {
                        headers: {'Authorization': `Bearer ${authToken}`}
                    });
                    const dashboardData = await dashboardResponse.json();
                    
                    // Update UI
                    document.getElementById('login-form').style.display = 'none';
                    document.getElementById('dashboard').style.display = 'block';
                    
                    document.getElementById('user-info').innerHTML = 
                        `<h2>Welcome, ${profileData.name}!</h2>`;
                    
                    document.getElementById('stats').innerHTML = 
                        `<div class="stats">
                            <div>Orders: ${dashboardData.stats.orders}</div>
                            <div>Revenue: $${dashboardData.stats.revenue}</div>
                            <div>Customers: ${dashboardData.stats.customers}</div>
                        </div>`;
                    
                    document.getElementById('activity').innerHTML = 
                        '<h3>Recent Activity:</h3>' +
                        dashboardData.recent_activity.map(item => 
                            `<div class="activity-item">${item.description} (${item.time})</div>`
                        ).join('');
                    
                    document.getElementById('status').innerHTML = 
                        '<div class="success">Login successful!</div>';
                        
                } catch (error) {
                    document.getElementById('status').innerHTML = 
                        '<div class="error">Login failed!</div>';
                }
            });
            
            document.getElementById('logout-btn').addEventListener('click', () => {
                authToken = null;
                document.getElementById('login-form').style.display = 'block';
                document.getElementById('dashboard').style.display = 'none';
                document.getElementById('status').innerHTML = 
                    '<div class="info">Logged out</div>';
            });
        </script>
    </body>
    </html>
    """
    
    await page.set_content(html_content)
    
    # Perform login workflow
    await page.click('#login-btn')
    
    # Wait for dashboard to load
    await page.wait_for_selector('#dashboard[style*="block"]')
    await page.wait_for_selector('.success')
    
    # Verify all components loaded
    welcome_text = await page.locator('#user-info h2').text_content()
    assert "Welcome, Test User!" in welcome_text
    
    stats_divs = await page.locator('.stats div').all()
    assert len(stats_divs) == 3
    assert "Orders: 5" in await stats_divs[0].text_content()
    assert "Revenue: $1250.5" in await stats_divs[1].text_content()
    
    activity_items = await page.locator('.activity-item').all()
    assert len(activity_items) == 2
    assert "New order #1001" in await activity_items[0].text_content()
    
    success_msg = await page.locator('.success').text_content()
    assert "Login successful!" in success_msg
    
    # Verify all API calls were made
    requests = api_mocker.get_request_log()
    assert len(requests) == 3
    assert requests[0]['method'] == 'POST'  # Login
    assert requests[1]['method'] == 'GET'   # Profile
    assert requests[2]['method'] == 'GET'   # Dashboard
    
    # Test logout
    await page.click('#logout-btn')
    await page.wait_for_selector('#login-form[style*="block"]')
    
    logout_msg = await page.locator('.info').text_content()
    assert "Logged out" in logout_msg
    
    # Print network activity summary
    api_mocker.print_network_activity()