"""
Visual Regression Testing Utilities
===================================

This module provides visual regression testing capabilities for Playwright tests.
It includes fixtures and helper functions for comparing screenshots with tolerance
thresholds and automatic diff generation.

Features:
    ✓ Baseline screenshot management
    ✓ Tolerance-based comparison (percentage of different pixels)
    ✓ Automatic diff image generation
    ✓ Full page or element-specific screenshots
    ✓ Async/await support for Playwright
    ✓ Integration with pytest fixtures

Usage:
    # In your test file
    @pytest.mark.asyncio
    async def test_homepage_visual(page, visual_regression):
        await page.goto("https://example.com")
        await visual_regression("homepage", tolerance=0.02)

    # Element-specific screenshot
    await visual_regression("header", selector="#header", tolerance=0.01)

Directory Structure:
    visual_baselines/  - Reference screenshots
    visual_current/    - Current test screenshots  
    visual_diffs/      - Diff images when tests fail

Dependencies:
    - playwright.async_api: Async Playwright Page object
    - pytest_asyncio: Async fixture support
    - PIL (Pillow): Image manipulation and comparison
    - numpy: Efficient array operations for pixel comparison
    - opencv-python (cv2): Advanced diff visualization with highlighted regions

Author: Generated for Playwright visual regression testing
"""

import os
import pytest
import pytest_asyncio
import numpy as np
from playwright.async_api import Page
from PIL import Image, ImageChops

# Directory configuration for visual regression files
BASELINE_DIR = "test_artifacts/visual/visual_baselines"
CURRENT_DIR = "test_artifacts/visual/visual_current"
DIFF_DIR = "test_artifacts/visual/visual_diffs"

# Ensure directories exist
os.makedirs(BASELINE_DIR, exist_ok=True)
os.makedirs(CURRENT_DIR, exist_ok=True)
os.makedirs(DIFF_DIR, exist_ok=True)


def compare_images(baseline_path, current_path, diff_path, tolerance=0.01):
    """
    Compare two images with a tolerance threshold for pixel differences.
    
    This function loads two images, computes their pixel-wise difference,
    and determines if the percentage of different pixels exceeds the tolerance.
    If differences exceed tolerance, a diff image is saved highlighting changes.
    
    Args:
        baseline_path (str): Path to the baseline/reference image
        current_path (str): Path to the current test screenshot
        diff_path (str): Path where diff image should be saved if different
        tolerance (float): Maximum allowed fraction of different pixels (0.01 = 1%)
        
    Returns:
        tuple: (matches: bool, diff_ratio: float)
            - matches: True if images are within tolerance, False otherwise
            - diff_ratio: Actual fraction of pixels that differ
            
    Example:
        matches, ratio = compare_images("baseline.png", "current.png", "diff.png", 0.02)
        if not matches:
            print(f"Images differ by {ratio:.2%}")
    """
    try:
        # Load images and convert to RGB for consistent comparison
        img1 = Image.open(baseline_path).convert("RGB")
        img2 = Image.open(current_path).convert("RGB")
        
        # Ensure images are the same size
        if img1.size != img2.size:
            print(f"Warning: Image size mismatch - baseline: {img1.size}, current: {img2.size}")
            # Resize current to match baseline
            img2 = img2.resize(img1.size, Image.Resampling.LANCZOS)
        
        # Compute pixel-wise difference
        diff = ImageChops.difference(img1, img2)
        diff_array = np.array(diff)
        
        # Count pixels that have any difference (non-zero in any channel)
        # diff_array.shape is (height, width, channels)
        diff_pixels = np.count_nonzero(np.any(diff_array, axis=2))
        total_pixels = diff_array.shape[0] * diff_array.shape[1]
        
        # Calculate the ratio of different pixels
        diff_ratio = diff_pixels / total_pixels if total_pixels > 0 else 0
        
        # Save diff image if differences exceed tolerance
        if diff_ratio > tolerance:
            diff.save(diff_path)
            return False, diff_ratio
            
        return True, diff_ratio
        
    except Exception as e:
        print(f"Error comparing images: {e}")
        return False, 1.0  # Assume complete difference on error


def get_screenshot_paths(name):
    """
    Generate file paths for baseline, current, and diff screenshots.
    
    Args:
        name (str): Base name for the screenshot files
        
    Returns:
        tuple: (baseline_path, current_path, diff_path)
    """
    baseline_path = os.path.join(BASELINE_DIR, f"{name}.png")
    current_path = os.path.join(CURRENT_DIR, f"{name}.png") 
    diff_path = os.path.join(DIFF_DIR, f"{name}_diff.png")
    
    return baseline_path, current_path, diff_path


@pytest_asyncio.fixture
async def visual_regression(page: Page):
    """
    Async pytest fixture for visual regression testing with Playwright.
    
    This fixture provides a comparison function that can take screenshots
    of full pages or specific elements, compare them against baselines,
    and fail tests when visual changes exceed tolerance thresholds.
    
    The fixture handles:
    - Baseline creation on first run
    - Screenshot capture (full page or element-specific)
    - Image comparison with tolerance
    - Diff generation for failed comparisons
    - Clear error messages with diff percentages
    
    Args:
        page (Page): Playwright Page object from the page fixture
        
    Yields:
        function: Async comparison function with signature:
            async def _compare(name, selector=None, full_page=True, tolerance=0.01)
            
    Example Usage:
        @pytest.mark.asyncio
        async def test_homepage(page, visual_regression):
            await page.goto("https://example.com")
            
            # Full page screenshot with 2% tolerance
            await visual_regression("homepage", tolerance=0.02)
            
            # Element-specific screenshot
            await visual_regression("header", selector="#main-header", tolerance=0.01)
    """
    
    async def _compare(name: str, selector: str = None, full_page: bool = True, tolerance: float = 0.01):
        """
        Compare current page/element screenshot against baseline.
        
        Args:
            name (str): Unique name for this visual test (used for file naming)
            selector (str, optional): CSS selector for element-specific screenshot
            full_page (bool): Whether to capture full page (ignored if selector provided)
            tolerance (float): Maximum allowed difference ratio (0.01 = 1%)
            
        Raises:
            AssertionError: If visual differences exceed tolerance threshold
            pytest.skip: On first run when baseline is created
        """
        baseline_path, current_path, diff_path = get_screenshot_paths(name)
        
        try:
            # Capture screenshot based on selector or full page
            if selector:
                await page.locator(selector).screenshot(path=current_path)
            else:
                await page.screenshot(path=current_path, full_page=full_page)
                
        except Exception as e:
            pytest.fail(f"Failed to capture screenshot for '{name}': {e}")
        
        # First run: create baseline and skip test
        if not os.path.exists(baseline_path):
            try:
                os.rename(current_path, baseline_path)
                pytest.skip(f"✅ Baseline created for '{name}'. Re-run test to perform comparison.")
            except Exception as e:
                pytest.fail(f"Failed to create baseline for '{name}': {e}")
        
        # Subsequent runs: compare against baseline
        try:
            matches, diff_ratio = compare_images(baseline_path, current_path, diff_path, tolerance)
            
            if not matches:
                # Clean up current screenshot on failure (keep baseline and diff)
                if os.path.exists(current_path):
                    os.remove(current_path)
                    
                assert False, (
                    f"🔍 Visual regression detected for '{name}'\n"
                    f"   Difference: {diff_ratio:.2%} (threshold: {tolerance:.2%})\n"
                    f"   Diff image: {diff_path}\n"
                    f"   Baseline: {baseline_path}"
                )
            else:
                # Test passed - clean up current screenshot
                if os.path.exists(current_path):
                    os.remove(current_path)
                    
                print(f"✅ Visual regression passed for '{name}' (diff: {diff_ratio:.2%})")
                
        except AssertionError:
            # Re-raise assertion errors (test failures)
            raise
        except Exception as e:
            pytest.fail(f"Error during visual comparison for '{name}': {e}")
    
    return _compare


def reset_baseline(name: str):
    """
    Utility function to reset a specific baseline image.
    Useful for updating baselines when intentional changes are made.
    
    Args:
        name (str): Name of the baseline to reset
        
    Returns:
        bool: True if baseline was removed, False if it didn't exist
    """
    baseline_path = os.path.join(BASELINE_DIR, f"{name}.png")
    
    if os.path.exists(baseline_path):
        os.remove(baseline_path)
        print(f"🗑️  Baseline reset for '{name}'")
        return True
    else:
        print(f"⚠️  No baseline found for '{name}'")
        return False


def reset_all_baselines():
    """
    Utility function to reset all baseline images.
    Use with caution - this will cause all visual tests to recreate baselines.
    
    Returns:
        int: Number of baselines that were removed
    """
    if not os.path.exists(BASELINE_DIR):
        print("⚠️  No baseline directory found")
        return 0
        
    baselines = [f for f in os.listdir(BASELINE_DIR) if f.endswith('.png')]
    
    for baseline in baselines:
        os.remove(os.path.join(BASELINE_DIR, baseline))
        
    print(f"🗑️  Reset {len(baselines)} baselines")
    return len(baselines)


def list_visual_files():
    """
    Utility function to list all visual regression files.
    Helpful for debugging and understanding test state.
    
    Returns:
        dict: Dictionary with lists of files in each directory
    """
    result = {
        'baselines': [],
        'current': [],
        'diffs': []
    }
    
    if os.path.exists(BASELINE_DIR):
        result['baselines'] = [f for f in os.listdir(BASELINE_DIR) if f.endswith('.png')]
        
    if os.path.exists(CURRENT_DIR):
        result['current'] = [f for f in os.listdir(CURRENT_DIR) if f.endswith('.png')]
        
    if os.path.exists(DIFF_DIR):
        result['diffs'] = [f for f in os.listdir(DIFF_DIR) if f.endswith('.png')]
    
    return result