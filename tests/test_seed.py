"""
===============================================================================
Seed Test for the Playwright Test Agents (Planner / Generator)
===============================================================================
Minimal bootstrap the generator uses as a starting point. Not part of the
marker-selected CI suites; run ad hoc against a configured BASE_URL.

Author: PMAC
Site: The Internet (https://the-internet.herokuapp.com)
===============================================================================
"""
import os


async def test_seed(page):
    # generate steps here
    await page.goto(os.getenv("BASE_URL", "https://the-internet.herokuapp.com"))
