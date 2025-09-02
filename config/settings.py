"""
Configuration settings for the Generic Playwright AI Test Framework.
Loads environment variables and provides default values for tests.
"""
import os


class Settings:
    # Base URLs for test sites
    BASE_URL = os.getenv("BASE_URL", "https://the-internet.herokuapp.com")
    API_LOGIN_URL = os.getenv(
        "API_LOGIN_URL", "https://the-internet.herokuapp.com/login"
    )
    
    # Test Users (The Internet test site)
    DEMO_USER = {
        "username": os.getenv("USER_DEMO_USERNAME", "tomsmith"),
        "password": os.getenv("USER_DEMO_PASSWORD", "SuperSecretPassword!"),
        "role": "demo_user"
    }
    
    ADMIN_USER = {
        "username": os.getenv("USER_ADMIN_USERNAME", "admin"),
        "password": os.getenv("USER_ADMIN_PASSWORD", "admin123"),
        "role": "admin"
    }
    
    # Browser Configuration
    BROWSER = os.getenv("BROWSER", "chromium")
    HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
    SLOW_MO = int(os.getenv("SLOW_MO", "100"))
    
    # Timeouts
    DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "30000"))
    NAVIGATION_TIMEOUT = int(os.getenv("NAVIGATION_TIMEOUT", "30000"))
    
    # Test Configuration
    RETRY_COUNT = int(os.getenv("RETRY_COUNT", "3"))
    RETRY_DELAY = int(os.getenv("RETRY_DELAY", "1000"))
    SCREENSHOT_ON_FAILURE = (
        os.getenv("SCREENSHOT_ON_FAILURE", "true").lower() == "true"
    )
    VIDEO_ON_FAILURE = (
        os.getenv("VIDEO_ON_FAILURE", "true").lower() == "true"
    )
    
    # AI Healing
    AI_HEALING_ENABLED = (
        os.getenv("AI_HEALING_ENABLED", "false").lower() == "true"
    )
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    
    # Debug
    DEBUG_MSG = os.getenv("DEBUG_MSG", "false").lower() == "true"
    
    # Allure Configuration
    ALLURE_RESULTS_DIR = os.getenv(
        "ALLURE_RESULTS_DIR", "test_artifacts/allure/allure-results"
    )
    
    @classmethod
    def get_browser_options(cls) -> dict:
        """Get browser launch options."""
        return {
            "headless": cls.HEADLESS,
            "slow_mo": cls.SLOW_MO,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ] if os.getenv("CI") else []
        }


# Create a global settings instance
settings = Settings()
