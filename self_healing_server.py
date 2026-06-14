import asyncio
import os
import json
import dotenv
from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright
from google import genai
from google.genai import types as genai_types

# Load environment variables (such as GEMINI_API_KEY)
dotenv.load_dotenv()

# Initialize FastMCP Server
mcp = FastMCP("awarse")

class PlaywrightBrowser:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def get_page(self):
        if self.page is None:
            print("[AWARSE] Launching headless browser...")
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
        return self.page

    async def close(self):
        print("[AWARSE] Closing browser...")
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None

# Global browser manager instance
browser_manager = PlaywrightBrowser()

async def heal_selector(page, failed_selector: str, action_type: str) -> str:
    """Uses Gemini API to heal a failed selector by analyzing the DOM state."""
    # Capture current DOM interactive elements
    dom_snapshot = await page.evaluate("""() => {
        const elements = Array.from(document.querySelectorAll('input, button, select, textarea, a, [role="button"], [class*="btn"]'));
        return elements.map((el, index) => {
            return {
                index: index,
                tagName: el.tagName,
                id: el.id,
                className: el.className,
                text: el.innerText || el.value || '',
                type: el.type || '',
                role: el.getAttribute('role') || '',
                name: el.getAttribute('name') || '',
                placeholder: el.getAttribute('placeholder') || '',
                ariaLabel: el.getAttribute('aria-label') || ''
            };
        });
    }""")
    
    # Retrieve page HTML for small-page full context
    html_content = await page.content()
    
    # Format simplified DOM representation
    dom_str = json.dumps(dom_snapshot, indent=2)
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment.")
        
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
You are the self-healing engine of AWARSE (Autonomous Web-Automation Runtime Self-Healing Engine).
A web interaction '{action_type}' failed because the selector '{failed_selector}' could not be located.
The structure of the web page has changed. Your task is to identify the new selector for the intended element.

Here is the list of interactive elements found on the page:
```json
{dom_str}
```

And here is the raw HTML body context (first 10000 characters):
```html
{html_content[:10000]}
```

Based on the old selector '{failed_selector}' and the current page elements, identify the intended target.
Provide a corrected, working CSS selector for that element.

Return ONLY a JSON object matching this structure:
{{
  "healed_selector": "working CSS selector (e.g., 'button.btn-primary' or 'input#email')",
  "explanation": "Brief reasoning for selecting this element",
  "confidence": 0.0 to 1.0
}}
"""
    
    print(f"[AWARSE Healer] Invoking Gemini model (gemini-2.5-flash) to heal selector...")
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    
    try:
        result = json.loads(response.text)
        healed = result.get("healed_selector")
        print(f"[AWARSE Healer] HEALED: '{failed_selector}' -> '{healed}' (confidence: {result.get('confidence')})")
        print(f"[AWARSE Healer] REASON: {result.get('explanation')}")
        return healed
    except Exception as e:
        print(f"[AWARSE Healer] Failed to parse healer response: {e}. Raw response: {response.text}")
        raise

@mcp.tool()
async def navigate(url: str) -> str:
    """Navigate the browser to a given URL."""
    page = await browser_manager.get_page()
    print(f"[AWARSE] Navigating to: {url}")
    await page.goto(url)
    return f"Successfully navigated to {url}"

@mcp.tool()
async def click_element(selector: str) -> str:
    """Click an element on the page. Automatically heals the selector if it fails."""
    page = await browser_manager.get_page()
    try:
        print(f"[AWARSE] Clicking element: {selector}")
        await page.click(selector, timeout=3000)
        return f"Successfully clicked element: {selector}"
    except Exception as e:
        print(f"[AWARSE] Click failed for selector '{selector}'. Attempting self-healing...")
        try:
            healed = await heal_selector(page, selector, "click")
            if healed:
                print(f"[AWARSE] Retrying click with healed selector: {healed}")
                await page.click(healed, timeout=5000)
                return f"Successfully clicked element after self-healing. Selector healed from '{selector}' to '{healed}'"
        except Exception as heal_err:
            return f"Failed to click element. Selector '{selector}' failed, and self-healing failed with error: {heal_err}"
        return f"Failed to click element: {e}"

@mcp.tool()
async def fill_element(selector: str, value: str) -> str:
    """Fill a form field with a value. Automatically heals the selector if it fails."""
    page = await browser_manager.get_page()
    try:
        print(f"[AWARSE] Filling element '{selector}' with value...")
        await page.fill(selector, value, timeout=3000)
        return f"Successfully filled element: {selector}"
    except Exception as e:
        print(f"[AWARSE] Fill failed for selector '{selector}'. Attempting self-healing...")
        try:
            healed = await heal_selector(page, selector, "fill")
            if healed:
                print(f"[AWARSE] Retrying fill with healed selector: {healed}")
                await page.fill(healed, value, timeout=5000)
                return f"Successfully filled element after self-healing. Selector healed from '{selector}' to '{healed}'"
        except Exception as heal_err:
            return f"Failed to fill element. Selector '{selector}' failed, and self-healing failed with error: {heal_err}"
        return f"Failed to fill element: {e}"

@mcp.tool()
async def get_content() -> str:
    """Retrieve the inner text content of the current page."""
    page = await browser_manager.get_page()
    text = await page.evaluate("() => document.body.innerText")
    return text

@mcp.tool()
async def evaluate_js(script: str) -> str:
    """Evaluate a JavaScript string on the current page."""
    page = await browser_manager.get_page()
    result = await page.evaluate(script)
    return f"JS evaluation returned: {result}"

@mcp.tool()
async def take_screenshot(filename: str = "screenshot.png") -> str:
    """Take a screenshot of the current page and save it locally."""
    page = await browser_manager.get_page()
    filepath = os.path.abspath(filename)
    print(f"[AWARSE] Saving screenshot to: {filepath}")
    await page.screenshot(path=filepath)
    return f"Screenshot saved successfully to {filepath}"

if __name__ == "__main__":
    # Start the FastMCP server
    mcp.run()
