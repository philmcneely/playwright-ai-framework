import os

# ------------------------------------------------------------------------------
# Function: is_browserstack_enabled
# ------------------------------------------------------------------------------

def is_browserstack_enabled():
    """
    Helper function to check if BrowserStack integration is enabled based on the BROWSERSTACK_ENABLED environment variable.
    Returns True if BROWSERSTACK_ENABLED is set to "true" (case-insensitive), otherwise returns False.
    """

    return os.getenv("BROWSERSTACK_ENABLED", "false").lower() == "true"