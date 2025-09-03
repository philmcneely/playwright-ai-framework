"""
===============================================================================
Visual Regression Test Suite for The Internet Test Site
===============================================================================

This module contains comprehensive visual regression tests that verify the
visual appearance and layout consistency of The Internet test site pages.
It includes tests for baseline creation, change detection, and diff generation.

Features:
    ✓ Baseline screenshot creation for new tests
    ✓ Visual change detection with configurable thresholds
    ✓ Automatic diff generation for failed visual comparisons
    ✓ Support for different page layouts and components
    ✓ Integration with visual regression testing framework

Test Categories:
    • Baseline Tests: Create reference screenshots for visual comparison
    • Change Detection: Verify visual consistency across test runs
    • Threshold Testing: Test sensitivity to visual changes
    • Component Testing: Test individual page components

Usage Examples:
    # Run all visual regression tests
    pytest tests/visual_regression/test_visual_regression.py -v 

    # Run just the failing test to see diff generation
    pytest tests/visual_regression/test_visual_regression.py::test_homepage_visual_major_change_should_fail -v

Author: PMAC
Site: The Internet (https://the-internet.herokuapp.com)
Date: [2025-09-03]
===============================================================================
"""

import pytest
import os
from playwright.async_api import Page


@pytest.mark.asyncio
async def test_homepage_visual_baseline(page: Page, visual_regression):
    """
    Test that creates a baseline screenshot of a simple HTML page.
    This should pass on first run (creates baseline) and subsequent runs.
    """
    # Create a simple HTML page
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Visual Regression Test</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                margin: 40px;
                background-color: #f0f0f0;
            }
            .header { 
                background-color: #4CAF50; 
                color: white; 
                padding: 20px; 
                text-align: center;
                border-radius: 8px;
            }
            .content { 
                background-color: white; 
                padding: 30px; 
                margin-top: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .button {
                background-color: #008CBA;
                color: white;
                padding: 15px 32px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
                margin: 10px;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Visual Regression Testing</h1>
        </div>
        <div class="content">
            <h2>Welcome to our test page</h2>
            <p>This page is used to test visual regression detection.</p>
            <button class="button">Click Me</button>
            <button class="button">Another Button</button>
        </div>
    </body>
    </html>
    """
    
    await page.set_content(html_content)
    await page.wait_for_load_state("networkidle")
    
    # Take baseline screenshot with 1% tolerance
    await visual_regression("homepage_baseline", tolerance=0.01)


@pytest.mark.asyncio
async def test_homepage_visual_small_change(page: Page, visual_regression):
    """
    Test with a small change that should stay within tolerance.
    Changes button text slightly - should pass with 2% tolerance.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Visual Regression Test</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                margin: 40px;
                background-color: #f0f0f0;
            }
            .header { 
                background-color: #4CAF50; 
                color: white; 
                padding: 20px; 
                text-align: center;
                border-radius: 8px;
            }
            .content { 
                background-color: white; 
                padding: 30px; 
                margin-top: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .button {
                background-color: #008CBA;
                color: white;
                padding: 15px 32px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
                margin: 10px;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Visual Regression Testing</h1>
        </div>
        <div class="content">
            <h2>Welcome to our test page</h2>
            <p>This page is used to test visual regression detection.</p>
            <button class="button">Click Here</button>  <!-- Small text change -->
            <button class="button">Another Button</button>
        </div>
    </body>
    </html>
    """
    
    await page.set_content(html_content)
    await page.wait_for_load_state("networkidle")
    
    # Should pass with higher tolerance
    await visual_regression("small_change_test", tolerance=0.02)


@pytest.mark.asyncio
async def test_homepage_visual_major_change_should_fail(page: Page, visual_regression):
    """
    Test with EXTREME visual changes that will definitely exceed threshold and fail.
    This creates a completely different page layout to guarantee failure.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>COMPLETELY DIFFERENT PAGE</title>
        <style>
            body { 
                font-family: 'Comic Sans MS', cursive; 
                margin: 0;
                padding: 0;
                background: linear-gradient(45deg, #ff0000, #00ff00, #0000ff, #ffff00);
                background-size: 400% 400%;
                animation: gradient 15s ease infinite;
                min-height: 100vh;
            }
            @keyframes gradient {
                0% { background-position: 0% 50%; }
                50% { background-position: 100% 50%; }
                100% { background-position: 0% 50%; }
            }
            .container {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                text-align: center;
            }
            .mega-header { 
                background-color: black;
                color: lime;
                padding: 50px; 
                font-size: 48px;
                border: 10px solid red;
                transform: rotate(-5deg);
                box-shadow: 20px 20px 0px purple;
            }
            .crazy-content { 
                background-color: yellow; 
                color: red;
                padding: 40px; 
                margin: 30px;
                border: 5px dashed blue;
                transform: skew(-10deg);
                font-size: 24px;
            }
            .wild-button {
                background: radial-gradient(circle, orange, purple);
                color: white;
                padding: 30px 60px;
                border: 5px solid black;
                border-radius: 50px;
                font-size: 20px;
                margin: 20px;
                transform: scale(1.5);
                box-shadow: 10px 10px 20px rgba(0,0,0,0.5);
            }
            .floating-box {
                position: absolute;
                top: 10px;
                right: 10px;
                width: 200px;
                height: 200px;
                background: conic-gradient(red, yellow, lime, aqua, blue, magenta, red);
                border-radius: 50%;
                animation: spin 3s linear infinite;
            }
            @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }
        </style>
    </head>
    <body>
        <div class="floating-box"></div>
        <div class="container">
            <div class="mega-header">
                <h1>🚨 EXTREME VISUAL CHANGE! 🚨</h1>
            </div>
            <div class="crazy-content">
                <h2>THIS IS COMPLETELY DIFFERENT!</h2>
                <p>Rainbow backgrounds! Rotated elements! Animations!</p>
                <p>This should definitely exceed any reasonable threshold!</p>
            </div>
            <button class="wild-button">GIANT BUTTON</button>
            <button class="wild-button">ANOTHER GIANT BUTTON</button>
            <div style="background: black; color: white; padding: 20px; margin: 20px; font-size: 30px;">
                <h3>🎨 EXTRA CONTENT BLOCK 🎨</h3>
                <p>More visual noise to ensure threshold breach!</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    await page.set_content(html_content)
    await page.wait_for_load_state("networkidle")
    
    # This should DEFINITELY fail with even a very high tolerance
    # Using pytest.raises to expect the assertion error
    with pytest.raises(AssertionError, match="Visual regression detected"):
        await visual_regression("major_change_test", tolerance=0.01)  # Lower tolerance to ensure failure


@pytest.mark.asyncio
async def test_element_specific_visual_regression(page: Page, visual_regression):
    """
    Test visual regression on a specific element rather than full page.
    Tests the selector parameter of the visual regression fixture.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Element-Specific Test</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .header { 
                background-color: #4CAF50; 
                color: white; 
                padding: 20px; 
                text-align: center;
                border-radius: 8px;
            }
            .content { 
                background-color: white; 
                padding: 30px; 
                margin-top: 20px;
            }
        </style>
    </head>
    <body>
        <div class="header" id="test-header">
            <h1>Header Element Test</h1>
        </div>
        <div class="content">
            <p>This content should not affect header-only screenshot</p>
        </div>
    </body>
    </html>
    """
    
    await page.set_content(html_content)
    await page.wait_for_load_state("networkidle")
    
    # Test screenshot of specific element only
    await visual_regression("header_element", selector="#test-header", tolerance=0.01)


@pytest.mark.asyncio 
async def test_cleanup_visual_files():
    """
    Utility test to check that visual regression files are being created.
    This helps verify the fixture is working correctly.
    """
    # Check that directories exist
    assert os.path.exists("test_artifacts/visual/visual_baselines"), "Baseline directory should exist"
    assert os.path.exists("test_artifacts/visual/visual_current"), "Current directory should exist"
    assert os.path.exists("test_artifacts/visual/visual_diffs"), "Diff directory should exist"

    # List files in each directory for debugging
    baseline_files = os.listdir("test_artifacts/visual/visual_baselines") if os.path.exists("test_artifacts/visual/visual_baselines") else []
    current_files = os.listdir("test_artifacts/visual/visual_current") if os.path.exists("test_artifacts/visual/visual_current") else []
    diff_files = os.listdir("test_artifacts/visual/visual_diffs") if os.path.exists("test_artifacts/visual/visual_diffs") else []

    print(f"\n📁 Visual regression files:")
    print(f"   Baselines: {baseline_files}")
    print(f"   Current: {current_files}")
    print(f"   Diffs: {diff_files}")