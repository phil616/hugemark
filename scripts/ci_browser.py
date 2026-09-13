"""Expose the pinned Playwright browser location to subsequent Actions steps."""
import os
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    path = p.chromium.executable_path
with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as stream:
    stream.write('CHROME_PATH=' + path + '\n')
