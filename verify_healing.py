import asyncio
import os
import dotenv
from playwright.async_api import async_playwright
from self_healing_server import heal_selector

dotenv.load_dotenv()

async def main():
    print("[TEST] Starting direct self-healing verification...")
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Resolve test page URL
        test_page_path = os.path.abspath("test_page.html")
        test_page_url = f"file://{test_page_path}"
        
        # 1. Navigate to the page
        print(f"[TEST] Navigating to: {test_page_url}")
        await page.goto(test_page_url)
        
        # 2. Fill form fields
        print("[TEST] Filling username and email...")
        await page.fill("#username", "healer_direct_test")
        await page.fill("#email", "healer_direct@test.local")
        
        # 3. Simulate UI redesign by calling mutateDOM()
        print("[TEST] Evaluating mutateDOM() JavaScript...")
        await page.evaluate("mutateDOM()")
        
        # 4. Attempt to click original selector (which is now broken)
        selector = "#submit-btn"
        print(f"[TEST] Attempting to click original selector '{selector}'...")
        try:
            # We use a short timeout (1 second) to simulate failure quickly
            await page.click(selector, timeout=1000)
            print("[TEST] Unexpected success clicking the original selector!")
        except Exception as e:
            print(f"[TEST] Click failed as expected due to selector mismatch: {e}")
            print("[TEST] Triggering self-healing routine...")
            
            # Call our self-healing logic directly
            healed = await heal_selector(page, selector, "click")
            print(f"[TEST] Self-healing returned selector: '{healed}'")
            
            # Click with healed selector
            print(f"[TEST] Retrying click with healed selector '{healed}'...")
            await page.click(healed, timeout=2000)
            
        # 5. Verify status text
        status_text = await page.inner_text("#status")
        print(f"[TEST] Page status text: '{status_text}'")
        assert "submitted successfully via HEALED button" in status_text, "Verification failed!"
        print("[TEST] SUCCESS: Form submitted successfully via the healed button selector!")
        
        # 6. Capture screenshot
        screenshot_path = os.path.abspath("healed_submission.png")
        await page.screenshot(path=screenshot_path)
        print(f"[TEST] Screenshot saved to: {screenshot_path}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
