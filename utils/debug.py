import os

# ------------------------------------------------------------------------------
# Function: debug_print
# ------------------------------------------------------------------------------

def debug_print(*args, **kwargs):
    """
    Helper function for conditional debug printing based on the DEBUG_MSG environment variable.
    Prints messages only if DEBUG_MSG is set to "true" (case-insensitive).
    Useful for enabling or disabling verbose debug output without code changes.
    """
    if os.getenv("DEBUG_MSG", "false").lower() == "true":
        print(*args, **kwargs)