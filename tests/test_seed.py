"""Seed test for the Playwright test agents (planner/generator).

Minimal bootstrap the generator uses as a starting point. Not part of the
marker-selected CI suites; run ad hoc against a configured BASE_URL.
"""
import os


async def test_seed(page):
    # generate steps here
    await page.goto(os.getenv("BASE_URL", "https://the-internet.herokuapp.com"))
