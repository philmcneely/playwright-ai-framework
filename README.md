# Generic Playwright AI Test Framework

A comprehensive test automation framework built with Python, Playwright, and AI-powered healing capabilities. This framework provides a robust foundation for web application testing with intelligent test failure analysis and automated recovery.

## Features

- **Cross-Browser Testing**: Support for Chromium, Firefox, and WebKit
- **AI-Powered Healing**: Automatic test failure analysis using Ollama
- **Visual Regression**: Screenshot comparison and visual testing
- **Performance Monitoring**: Built-in performance tracking
- **Allure Reporting**: Comprehensive test reporting with screenshots and artifacts
- **Page Object Model**: Clean, maintainable page object architecture
- **Async/Await Support**: Modern Python async testing patterns
- **Debug Capabilities**: Comprehensive logging and debugging tools

## Quick Start

### Prerequisites

- Python 3.8 or higher
- Node.js (for Playwright browser installation)
- Ollama (for AI healing capabilities)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd playwright-ai-framework
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Install Playwright browsers:
```bash
playwright install
```

4. Install and start Ollama (optional, for AI healing):
```bash
# Follow Ollama installation instructions for your OS
ollama serve
ollama pull llama3.1:8b
```

### Running Tests

Run all tests:
```bash
pytest
```

Run smoke tests only:
```bash
pytest -m smoke
```

Run with debug output:
```bash
DEBUG_MSG=true pytest
```

Run with AI healing enabled:
```bash
AI_HEALING_ENABLED=true pytest
```

## Framework Structure

```
playwright-ai-framework/
├── config/              # Configuration files
│   ├── __init__.py
│   ├── settings.py      # Environment and test settings
│   └── artifact_paths.py # Test artifact path management
├── pages/               # Page Object Model
│   ├── __init__.py
│   ├── app.py          # Main application page object
│   ├── base_page.py    # Base page class
│   ├── login_page.py   # Login page object
│   └── secure_page.py  # Secure area page object
├── test_data/          # Test data and personas
│   └── test_data.py    # User credentials and test data
├── tests/              # Test files
│   ├── __init__.py
│   ├── test_login.py   # Login functionality tests
│   └── test_smoke.py   # Smoke tests
├── utils/              # Utility modules
│   ├── __init__.py
│   ├── ai_healing.py   # AI-powered test healing
│   ├── context_capture.py # Failure context capture
│   ├── debug.py        # Debug utilities
│   └── decorators/     # Test decorators
├── test_artifacts/     # Test outputs
│   ├── ai/            # AI healing artifacts
│   ├── allure/        # Allure reports
│   ├── performance/   # Performance data
│   └── visual/        # Screenshots and visual diffs
├── conftest.py        # Pytest configuration
├── pytest.ini        # Pytest settings
└── requirements.txt   # Python dependencies
```

## Configuration

### Environment Variables

The framework uses environment variables for configuration:

```bash
# Browser Configuration
BROWSER=chromium          # chromium, firefox, webkit
HEADLESS=false           # true/false
SLOW_MO=100              # Delay between actions in ms

# Test Configuration
DEFAULT_TIMEOUT=30000    # Default timeout in ms
RETRY_COUNT=3            # Number of test retries
SCREENSHOT_ON_FAILURE=true # Capture screenshots on failure

# AI Healing
AI_HEALING_ENABLED=false # Enable AI-powered healing
OLLAMA_MODEL=llama3.1:8b # Ollama model to use
OLLAMA_HOST=http://localhost:11434 # Ollama server URL

# Debug
DEBUG_MSG=false          # Enable debug messages

# Test Site (The Internet)
BASE_URL=https://the-internet.herokuapp.com
USER_DEMO_USERNAME=tomsmith
USER_DEMO_PASSWORD=SuperSecretPassword!
```

### Settings File

Configuration is managed through `config/settings.py`:

```python
from config.settings import settings

# Access configuration
browser = settings.BROWSER
base_url = settings.BASE_URL
demo_user = settings.DEMO_USER
```

## Page Objects

The framework uses the Page Object Model pattern:

```python
from pages.app import App

async def test_login(page):
    app = App(page)
    
    # Navigate to login page
    await app.login.navigate()
    
    # Perform login
    await app.login.login_with_demo_user()
    
    # Verify success
    assert await app.secure.is_on_secure_page()
```

## AI Healing

The framework includes AI-powered test healing using Ollama:

```python
# Enable AI healing with environment variable
AI_HEALING_ENABLED=true pytest

# Or configure in code
from utils.ai_healing import get_ollama_service

service = get_ollama_service()
suggestions = await service.analyze_failure(context, screenshot)
```

## Test Data

Test data is organized in `test_data/test_data.py`:

```python
from test_data.test_data import VALID_USERS, INVALID_USERS

# Use predefined users
demo_user = VALID_USERS["demo_user"]
invalid_user = INVALID_USERS["invalid_username"]
```

## Debugging

Enable debug output for detailed logging:

```bash
DEBUG_MSG=true pytest -v -s
```

Debug utilities are available:

```python
from utils.debug import debug_print

debug_print("Custom debug message")
```

## Reporting

Generate Allure reports:

```bash
# Run tests with Allure
pytest --alluredir=test_artifacts/allure/allure-results

# Generate and serve report
allure generate test_artifacts/allure/allure-results -o test_artifacts/allure/allure-report
allure serve test_artifacts/allure/allure-results
```

## Contributing

1. Follow PEP 8 style guidelines
2. Add tests for new features
3. Update documentation for new functionality
4. Use type hints where appropriate
5. Add debug logging for troubleshooting

## Test Site

This framework is configured to test [The Internet](https://the-internet.herokuapp.com), a testing playground that provides various scenarios for web automation testing.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
