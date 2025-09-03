"""
Test data and user personas for The Internet test site.
"""

# Valid test users for The Internet test site
VALID_USERS = {
    "demo_user": {
        "username": "tomsmith",
        "password": "SuperSecretPassword!",
        "role": "demo_user",
        "description": "Standard demo user for testing"
    },
    "admin_user": {
        "username": "admin",
        "password": "admin123",
        "role": "admin",
        "description": "Admin user for elevated testing"
    }
}

# Invalid test users for negative testing
INVALID_USERS = {
    "invalid_username": {
        "username": "invaliduser",
        "password": "SuperSecretPassword!",
        "description": "User with invalid username"
    },
    "invalid_password": {
        "username": "tomsmith",
        "password": "wrongpassword",
        "description": "Valid username with wrong password"
    },
    "empty_username": {
        "username": "",
        "password": "SuperSecretPassword!",
        "description": "Empty username field"
    },
    "empty_password": {
        "username": "tomsmith",
        "password": "",
        "description": "Empty password field"
    },
    "both_empty": {
        "username": "",
        "password": "",
        "description": "Both fields empty"
    },
    "special_characters": {
        "username": "user@#$%",
        "password": "pass!@#$%^&*()",
        "description": "Username and password with special characters"
    }
}

# Test URLs for The Internet test site
TEST_URLS = {
    "base": "https://the-internet.herokuapp.com",
    "login": "https://the-internet.herokuapp.com/login",
    "secure": "https://the-internet.herokuapp.com/secure",
    "logout": "https://the-internet.herokuapp.com/logout"
}

# Expected messages
EXPECTED_MESSAGES = {
    "login_success": "You logged into a secure area!",
    "login_failure": "Your username is invalid!",
    "logout_success": "You logged out of the secure area!",
    "password_invalid": "Your password is invalid!",
    "invalid_username": "Your username is invalid!",
    "invalid_password": "Your password is invalid!",
    "secure_area_title": "Secure Area",
    "login_page_title": "Login Page"
}

# Test timeouts
TIMEOUTS = {
    "default": 30000,
    "short": 5000,
    "long": 60000
}

# Browser configurations for testing
BROWSER_CONFIGS = {
    "desktop": {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    },
    "tablet": {
        "viewport": {"width": 768, "height": 1024},
        "user_agent": (
            "Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X) "
            "AppleWebKit/605.1.15"
        )
    },
    "mobile": {
        "viewport": {"width": 375, "height": 667},
        "user_agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
            "AppleWebKit/605.1.15"
        )
    }
}
