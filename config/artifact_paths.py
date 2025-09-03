from pathlib import Path

ARTIFACT_ROOT = Path("test_artifacts")
ALLURE_REPORTS_DIR = ARTIFACT_ROOT / "allure" / "allure_reports"
ALLURE_RESULTS_DIR = ARTIFACT_ROOT / "allure" / "allure_results"
SCREENSHOT_DIR = ARTIFACT_ROOT / "allure" / "screenshots"
AI_HEALING_REPORT_DIR = ARTIFACT_ROOT / "ai" / "ai_healing_reports"
VISUAL_BASELINE_DIR = ARTIFACT_ROOT / "visual" / "visual_baselines"
VISUAL_CURRENT_DIR = ARTIFACT_ROOT / "visual" / "visual_current"
VISUAL_DIFF_DIR = ARTIFACT_ROOT / "visual" / "visual_diffs"
PERFORMANCE_REPORT_DIR = ARTIFACT_ROOT / "performance" / "performance_reports"
