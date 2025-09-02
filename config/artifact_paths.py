from pathlib import Path

# ------------------------------------------------------------------------------
# Centralized Artifact Paths Configuration
# ------------------------------------------------------------------------------

# Root directory for all test artifacts
ARTIFACT_ROOT = Path("test_artifacts")

# Allure reporting paths
ALLURE_ROOT = ARTIFACT_ROOT / "allure"
ALLURE_SCREENSHOT_DIR = ALLURE_ROOT / "screenshots"
ALLURE_RESULTS_DIR = ALLURE_ROOT / "allure-results"
ALLURE_REPORT_DIR = ALLURE_ROOT / "allure-report"

# AI Healing paths
AI_HEALING_ROOT = ARTIFACT_ROOT / "ai"
AI_HEALING_REPORT_DIR = AI_HEALING_ROOT / "ai_healing_reports"

# Visual regression paths
VISUAL_ROOT = ARTIFACT_ROOT / "visual"
VISUAL_BASELINE_DIR = VISUAL_ROOT / "visual_baselines"
VISUAL_CURRENT_DIR = VISUAL_ROOT / "visual_current"
VISUAL_DIFF_DIR = VISUAL_ROOT / "visual_diffs"

# Performance testing paths
PERFORMANCE_ROOT = ARTIFACT_ROOT / "performance"
PERFORMANCE_REPORT_DIR = PERFORMANCE_ROOT / "performance_reports"


def ensure_directories():
    """Create all artifact directories if they don't exist."""
    for path in [
        ALLURE_SCREENSHOT_DIR, ALLURE_RESULTS_DIR, ALLURE_REPORT_DIR,
        AI_HEALING_REPORT_DIR, VISUAL_BASELINE_DIR, VISUAL_CURRENT_DIR,
        VISUAL_DIFF_DIR, PERFORMANCE_REPORT_DIR
    ]:
        path.mkdir(parents=True, exist_ok=True)
