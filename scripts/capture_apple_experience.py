import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        )
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        print("Navigating to http://localhost:8000/ ...")
        await page.goto("http://localhost:8000/")
        await page.wait_for_timeout(1500)

        # Initial screen screenshot
        await page.screenshot(path="assets/apple_ui_initial.png")
        print("Captured assets/apple_ui_initial.png")

        # Click Execute Multi-Agent Review
        print("Clicking submit review...")
        await page.click("#btn-review")

        # Wait for results
        await page.wait_for_selector("#findings-list .finding-card, #findings-list .loading-stepper-card", timeout=10000)
        await page.wait_for_timeout(2000)

        # Capture dark mode result view
        await page.screenshot(path="assets/apple_ui_dark.png")
        print("Captured assets/apple_ui_dark.png")

        # Open Share Sheet modal
        print("Opening share sheet modal...")
        await page.click("button:has-text('Share')")
        await page.wait_for_timeout(600)
        await page.screenshot(path="assets/apple_share_sheet.png")
        print("Captured assets/apple_share_sheet.png")

        # Close share modal
        await page.click("#share-modal .btn-close-modal")
        await page.wait_for_timeout(400)

        # Click Auto-Heal Code
        print("Testing Auto-Heal Code...")
        autoheal_btn = await page.query_selector("#btn-editor-autoheal")
        if autoheal_btn and await autoheal_btn.is_visible():
            await autoheal_btn.click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path="assets/apple_ui_autohealed.png")
            print("Captured assets/apple_ui_autohealed.png")

        # Switch to Inspector Mode
        print("Switching to Inspector Mode...")
        await page.click("#mode-inspector")
        await page.wait_for_timeout(600)
        await page.screenshot(path="assets/apple_ui_inspector.png")
        print("Captured assets/apple_ui_inspector.png")

        # Toggle to Light Mode
        print("Toggling to Light Mode...")
        await page.click("#btn-theme-toggle")
        await page.wait_for_timeout(600)
        await page.screenshot(path="assets/apple_ui_light.png")
        print("Captured assets/apple_ui_light.png")

        await browser.close()
        print("All visual captures complete!")

if __name__ == "__main__":
    asyncio.run(main())
