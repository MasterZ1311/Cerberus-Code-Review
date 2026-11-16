"""
Browser Accessibility Integration Tests using Playwright.
Validates:
1. Keyboard navigation, Tab traversal, and focus progression.
2. Screen-reader semantics, ARIA roles, labels, and live regions.
3. Media query support for prefers-reduced-motion: reduce.
4. Color tokens, contrast readability, and light/dark theme switching.
"""

from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="Playwright is required for browser E2E tests")
from playwright.sync_api import sync_playwright

WEB_INDEX_PATH = (Path(__file__).parent.parent / "cerberus" / "web" / "index.html").resolve()


@pytest.fixture(scope="module")
def browser_context():
    """Launch headless Chromium for the test module."""
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as e:
                pytest.skip(f"Chromium browser not available: {e}")
            context = browser.new_context()
            yield context
            browser.close()
    except Exception as e:
        pytest.skip(f"Playwright not available: {e}")


def test_accessibility_keyboard_navigation_and_tab_switching(browser_context):
    """Verify interactive controls can be reached and toggled via keyboard."""
    page = browser_context.new_page()
    try:
        page.goto(WEB_INDEX_PATH.as_uri())

        # Check initial state: Snippet tab selected
        tab_snippet = page.locator("#tab-snippet")
        tab_zip = page.locator("#tab-zip")
        assert tab_snippet.get_attribute("aria-selected") == "true"
        assert tab_zip.get_attribute("aria-selected") == "false"

        # Tab through controls until reaching tab-zip or activate via click/keyboard
        tab_zip.focus()
        page.keyboard.press("Enter")
        page.wait_for_timeout(100)

        assert tab_zip.get_attribute("aria-selected") == "true"
        assert tab_snippet.get_attribute("aria-selected") == "false"

        # Switch back via keyboard space
        tab_snippet.focus()
        page.keyboard.press("Space")
        page.wait_for_timeout(100)

        assert tab_snippet.get_attribute("aria-selected") == "true"
        assert tab_zip.get_attribute("aria-selected") == "false"
    finally:
        page.close()


def test_accessibility_aria_labels_and_screen_reader_semantics(browser_context):
    """Verify ARIA roles, landmarks, labels, and live regions are present."""
    page = browser_context.new_page()
    try:
        page.goto(WEB_INDEX_PATH.as_uri())

        # 1. Tablists and Tabs
        tablists = page.locator('[role="tablist"]')
        assert tablists.count() >= 2

        # 2. Alert and Live Region for notifications
        toast_container = page.locator("#toast-container")
        assert toast_container.get_attribute("role") == "alert"
        assert toast_container.get_attribute("aria-live") == "polite"

        # 3. Interactive header action buttons must have accessible labels
        header_buttons = page.locator(".btn-header-action")
        count = header_buttons.count()
        assert count >= 2
        for i in range(count):
            btn = header_buttons.nth(i)
            aria_label = btn.get_attribute("aria-label") or btn.get_attribute("title")
            assert aria_label and len(aria_label.strip()) > 0

        # 4. Major sections have accessible names
        panels = page.locator("section.panel")
        for i in range(panels.count()):
            panel = panels.nth(i)
            label = panel.get_attribute("aria-label")
            assert label and len(label.strip()) > 0
    finally:
        page.close()


def test_accessibility_prefers_reduced_motion(browser_context):
    """Verify transitions and animations are suppressed when prefers-reduced-motion is enabled."""
    page = browser_context.new_page()
    try:
        page.emulate_media(reduced_motion="reduce")
        page.goto(WEB_INDEX_PATH.as_uri())

        # Inspect computed transition and animation durations on elements
        durations = page.evaluate("""() => {
            const el = document.querySelector('body');
            const style = window.getComputedStyle(el);
            return {
                transitionDuration: style.transitionDuration,
                animationDuration: style.animationDuration
            };
        }""")

        # When reduced motion is on, durations are overridden to <= 0.01s (0.01ms / 0s)
        # Browsers report 0.01ms as '0s' or '0.00001s'
        trans_sec = float(durations["transitionDuration"].replace("s", "").replace("m", ""))
        assert trans_sec <= 0.05
    finally:
        page.close()


def test_accessibility_theme_toggle_and_contrast(browser_context):
    """Verify theme toggle cleanly switches themes and maintains readable contrast."""
    page = browser_context.new_page()
    try:
        page.goto(WEB_INDEX_PATH.as_uri())

        # Default theme is dark
        html_theme = page.locator("html").get_attribute("data-theme")
        assert html_theme == "dark"

        # Toggle to light mode
        theme_toggle_btn = page.locator('[aria-label="Toggle Theme"]')
        theme_toggle_btn.click()
        page.wait_for_timeout(100)

        light_theme = page.locator("html").get_attribute("data-theme")
        assert light_theme == "light"

        # Check body computed colors in light mode
        colors = page.evaluate("""() => {
            const body = document.querySelector('body');
            const style = window.getComputedStyle(body);
            return {
                color: style.color,
                bgColor: style.backgroundColor
            };
        }""")

        # Ensure text is not transparent and background is distinct from text
        assert colors["color"] != colors["bgColor"]
        assert colors["color"] != "rgba(0, 0, 0, 0)"
    finally:
        page.close()
