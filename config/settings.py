"""
Configuration settings for the test framework.
Loads environment variables and provides default values.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
env = os.getenv("ENV", "dev")  # default to 'dev' if ENV is not set
dotenv_file = f".env.{env}"
load_dotenv(".env")  # always load base first
load_dotenv(dotenv_file, override=False)

class Settings:
    """Application settings loaded from environment variables."""
    # Base URL Configuration
    BASE_URL: str = os.getenv("BASE_URL", "https://the-internet.herokuapp.com")
    
    # Browser Configuration
    BROWSER: str = os.getenv("BROWSER", "chromium")
    HEADLESS: bool = os.getenv("HEADLESS", "false").lower() == "true"
    SLOW_MO: int = int(os.getenv("SLOW_MO", "100"))
    TIMEOUT: int = int(os.getenv("TIMEOUT", "30000"))
    
    # Test Configuration
    RETRY_COUNT: int = int(os.getenv("RETRY_COUNT", "3"))
    RETRY_DELAY: int = int(os.getenv("RETRY_DELAY", "1000"))
    SCREENSHOT_ON_FAILURE: bool = os.getenv("SCREENSHOT_ON_FAILURE", "true").lower() == "true"
    VIDEO_ON_FAILURE: bool = os.getenv("VIDEO_ON_FAILURE", "true").lower() == "true"
    
    # Allure Configuration - not using atm
    ALLURE_RESULTS_DIR: str = os.getenv("ALLURE_RESULTS_DIR", "test_artifacts/allure/allure-results")

    DEBUG_MSG: bool = os.getenv("DEBUG_MSG", "false").lower() == "true" 

    @classmethod
    def get_browser_options(cls, browser_name: str = "chromium") -> dict:
        """Get browser launch options based on browser type."""
        base_options = {
            "headless": cls.HEADLESS,
            "slow_mo": cls.SLOW_MO,
        }
        
        # Browser-specific arguments
        if browser_name.lower() == "chromium":
            base_options["args"] = [
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        elif browser_name.lower() == "firefox":
            # Firefox-specific preferences
            base_options["firefox_user_prefs"] = {
                "dom.webdriver.enabled": False,
                "useAutomationExtension": False,
                "general.platform.override": "",
                "general.useragent.override": ""
            }
        elif browser_name.lower() == "webkit":
            # WebKit doesn't need special args for automation hiding
            base_options["args"] = []
        else:
            # Default args for unknown browsers
            base_options["args"] = [
                "--disable-extensions",
                "--no-sandbox"
            ]
            
        return base_options


# Create a global settings instance
settings = Settings()
