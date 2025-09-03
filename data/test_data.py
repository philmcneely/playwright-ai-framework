
"""
Test data for negative testing scenarios including invalid credentials,
malicious inputs, and edge cases for form validation.
Updated for The Internet test site (username/password instead of email/password).
"""

# =====================================
# Invalid User Credentials for Testing
# =====================================
INVALID_USERS = {
    "invalid_username": {
        "username": "invaliduser",
        "password": "SuperSecretPassword!"
    },
    "invalid_password": {
        "username": "tomsmith",
        "password": "wrongpassword"
    },
    "empty_username": {
        "username": "",
        "password": "SuperSecretPassword!"
    },
    "empty_password": {
        "username": "tomsmith",
        "password": ""
    },
    "both_empty": {
        "username": "",
        "password": ""
    },
    "nonexistent_user": {
        "username": "nonexistentuser123",
        "password": "anypassword"
    }
}

# =====================================
# Expected Error Messages
# =====================================
EXPECTED_MESSAGES = {
    "invalid_username": "Your username is invalid!",
    "invalid_password": "Your password is invalid!",
    "login_success": "You logged into a secure area!",
    "logout_success": "You logged out of the secure area!",
    "login_page_title": "Login Page",
    "secure_area_title": "Secure Area",
    "base": "https://the-internet.herokuapp.com"
}

# =====================================
# Test URLs for The Internet Test Site  
# =====================================
TEST_URLS = {
    "base": "https://the-internet.herokuapp.com",
    "base_url": "https://the-internet.herokuapp.com",
    "login_page": "https://the-internet.herokuapp.com/login",
    "secure_page": "https://the-internet.herokuapp.com/secure",
    "home_page": "https://the-internet.herokuapp.com",
    "logout_url": "https://the-internet.herokuapp.com/logout"
}

# =====================================
# Invalid Passwords
# =====================================
INVALID_PASSWORDS = {
    "empty": "",
    "too_short": "123",
    "no_uppercase": "password123!",
    "no_lowercase": "PASSWORD123!",
    "no_numbers": "Password!",
    "no_special": "Password123",
    "only_spaces": "   ",
    "common_weak": [
        "password",
        "123456",
        "qwerty",
        "letmein",
        "admin",
        "welcome",
        "monkey",
        "dragon"
    ],
    "sequential": "123456789",
    "keyboard_pattern": "qwertyuiop",
    "repeated_chars": "aaaaaaa",
    "too_long": "a" * 129,  # Assuming 128 char limit
}

# =====================================
# Invalid Usernames (adapted from emails)
# =====================================
INVALID_USERNAMES = {
    "empty": "",
    "with_spaces": "user name",
    "special_chars": "user<>name",
    "with_at": "user@domain",
    "with_dots": "user..name",
    "starts_with_dot": ".username",
    "ends_with_dot": "username.",
    "too_long": "a" * 250,
    "unicode": "用户@domain.com",
    "sql_injection": "user'; DROP TABLE users;--@domain.com",
}

# =====================================
# SQL Injection Payloads
# =====================================
SQL_INJECTION_PAYLOADS = {
    "basic_or": "' OR '1'='1",
    "comment_bypass": "admin'--",
    "union_select": "' UNION SELECT * FROM users--",
    "drop_table": "'; DROP TABLE users;--",
    "boolean_blind": "' OR 1=1#",
    "time_based": "'; WAITFOR DELAY '00:00:05'--",
    "error_based": "' AND (SELECT COUNT(*) FROM information_schema.tables)>0--",
    "stacked_queries": "'; INSERT INTO users VALUES('hacker','pass');--",
}

# =====================================
# XSS Payloads
# =====================================
XSS_PAYLOADS = {
    "basic_script": "<script>alert('xss')</script>",
    "img_onerror": "<img src=x onerror=alert('xss')>",
    "svg_onload": "<svg onload=alert('xss')>",
    "javascript_protocol": "javascript:alert('xss')",
    "event_handler": "<div onmouseover=alert('xss')>hover</div>",
    "encoded": "%3Cscript%3Ealert('xss')%3C/script%3E",
    "iframe": "<iframe src=javascript:alert('xss')></iframe>",
    "body_onload": "<body onload=alert('xss')>",
}

# =====================================
# Command Injection Payloads
# =====================================
COMMAND_INJECTION_PAYLOADS = {
    "basic": "; ls",
    "pipe": "| whoami",
    "background": "& ping google.com",
    "chained": "&& cat /etc/passwd",
    "or_operator": "|| echo 'injected'",
    "backticks": "`whoami`",
    "dollar_paren": "$(whoami)",
    "newline": "\nls -la",
}

# =====================================
# Path Traversal Payloads
# =====================================
PATH_TRAVERSAL_PAYLOADS = {
    "basic": "../../../etc/passwd",
    "windows": "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
    "encoded": "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "double_encoded": "%252e%252e%252f",
    "unicode": "..%c0%af..%c0%af..%c0%afetc%c0%afpasswd",
    "null_byte": "../../../etc/passwd%00",
}

# =====================================
# Invalid Names/Text Fields
# =====================================
INVALID_NAMES = {
    "empty": "",
    "only_spaces": "   ",
    "numbers_only": "12345",
    "special_chars": "!@#$%^&*()",
    "too_long": "a" * 256,
    "html_tags": "<script>alert('xss')</script>",
    "sql_injection": "'; DROP TABLE users;--",
    "unicode": "用户名",
    "emoji": "👤🔥💯",
    "newlines": "First\nName",
    "tabs": "First\tName",
}

# =====================================
# Boundary Values
# =====================================
BOUNDARY_VALUES = {
    "max_int": 2147483647,
    "min_int": -2147483648,
    "zero": 0,
    "negative": -1,
    "float": 3.14159,
    "very_large": 999999999999999999999,
    "scientific": "1e10",
}

# =====================================
# Common Attack Strings
# =====================================
ATTACK_STRINGS = [
    # XSS
    "<script>alert('xss')</script>",
    "javascript:alert('xss')",
    "<img src=x onerror=alert('xss')>",
    
    # SQL Injection
    "' OR '1'='1",
    "'; DROP TABLE users;--",
    "' UNION SELECT * FROM users--",
    
    # Command Injection
    "; ls -la",
    "| whoami",
    "&& cat /etc/passwd",
    
    # Path Traversal
    "../../../etc/passwd",
    "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
    
    # LDAP Injection
    "*)(uid=*",
    "admin)(&(password=*))",
    
    # XML Injection
    "<?xml version='1.0'?><!DOCTYPE root [<!ENTITY test SYSTEM 'file:///etc/passwd'>]><root>&test;</root>",
]

# =====================================
# Invalid Emails
# =====================================
INVALID_EMAILS = {
    "empty": "",
    "no_at_symbol": "invalidemail.com",
    "multiple_at": "user@@domain.com",
    "no_domain": "user@",
    "no_username": "@domain.com",
    "invalid_domain": "user@.com",
    "spaces": "user name@domain.com",
    "special_chars": "user<>@domain.com",
    "no_tld": "user@domain",
    "double_dot": "user@domain..com",
    "starts_with_dot": ".user@domain.com",
    "ends_with_dot": "user.@domain.com",
    "too_long": "a" * 250 + "@domain.com",
    "unicode": "用户@domain.com",
    "sql_injection": "user'; DROP TABLE users;--@domain.com",
}

# =====================================
# Helper Functions
# =====================================
def get_random_invalid_email():
    """Get a random invalid email for testing."""
    import random
    return random.choice(list(INVALID_EMAILS.values()))

def get_random_sql_payload():
    """Get a random SQL injection payload."""
    import random
    return random.choice(list(SQL_INJECTION_PAYLOADS.values()))

def get_random_xss_payload():
    """Get a random XSS payload."""
    import random
    return random.choice(list(XSS_PAYLOADS.values()))