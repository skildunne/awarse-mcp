import asyncio
import os
import json
import dotenv
import threading
from datetime import datetime
from http.server import SimpleHTTPRequestHandler
import socketserver
from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright
from google import genai
from google.genai import types as genai_types

# Load environment variables (such as GEMINI_API_KEY)
dotenv.load_dotenv()

# Initialize FastMCP Server
mcp = FastMCP("awarse")

# In-memory log of healed selectors for the session
healed_logs = []

def start_dashboard(port=8080):
    class QuietHandler(SimpleHTTPRequestHandler):
        # Quiet console spam during stdio transport sessions
        def log_message(self, format, *args):
            return

    # Serve files from the directory where dashboard.html lives
    handler = QuietHandler
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            print(f"[*] AWARSE Dashboard running at http://localhost:{port}")
            httpd.serve_forever()
    except Exception as e:
        print(f"[!] Failed to start dashboard server: {e}")

# Spin up in a daemon thread so it closes when the main MCP server stops
threading.Thread(target=start_dashboard, daemon=True).start()

# Initialize empty healed_logs.json for the dashboard
try:
    server_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(server_dir, "healed_logs.json")
    with open(log_path, "w") as f:
        json.dump([], f, indent=2)
except Exception as init_err:
    pass

async def generate_markdown_snapshot(page) -> str:
    """Generates a highly token-efficient markdown representation of interactive elements, similar to playwright-cli."""
    # Playwright page vs Selenium driver snapshot extraction
    if hasattr(page, 'evaluate'):
        # Playwright
        snapshot_js = """() => {
            const elements = Array.from(document.querySelectorAll('input, button, select, textarea, a, [role="button"], [class*="btn"]'));
            let result = [];
            elements.forEach((el, index) => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0 || window.getComputedStyle(el).display === 'none') {
                    return;
                }
                
                const tagName = el.tagName.toLowerCase();
                const id = el.id ? `#${el.id}` : '';
                const className = el.className ? `.${el.className.trim().replace(/\\s+/g, '.')}` : '';
                const text = el.innerText || el.value || '';
                const type = el.getAttribute('type') ? `[type="${el.getAttribute('type')}"]` : '';
                const role = el.getAttribute('role') ? `[role="${el.getAttribute('role')}"]` : '';
                const name = el.getAttribute('name') ? `[name="${el.getAttribute('name')}"]` : '';
                const placeholder = el.getAttribute('placeholder') ? `[placeholder="${el.getAttribute('placeholder')}"]` : '';
                const ariaLabel = el.getAttribute('aria-label') ? `[aria-label="${el.getAttribute('aria-label')}"]` : '';
                
                let attrs = [id, className, type, role, name, placeholder, ariaLabel].filter(Boolean).join(' ');
                let item = `- [e${index}] <${tagName} ${attrs}> "${text.trim().substring(0, 50)}"`;
                result.push(item);
            });
            return result.join('\\n');
        }"""
        return await page.evaluate(snapshot_js)
    else:
        # Selenium
        snapshot_js = """
        const elements = Array.from(document.querySelectorAll('input, button, select, textarea, a, [role="button"], [class*="btn"]'));
        let result = [];
        elements.forEach((el, index) => {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0 || window.getComputedStyle(el).display === 'none') {
                return;
            }
            const tagName = el.tagName.toLowerCase();
            const id = el.id ? `#${el.id}` : '';
            const className = el.className ? `.${el.className.trim().replace(/\\s+/g, '.')}` : '';
            const text = el.innerText || el.value || '';
            const type = el.getAttribute('type') ? `[type="${el.getAttribute('type')}"]` : '';
            const role = el.getAttribute('role') ? `[role="${el.getAttribute('role')}"]` : '';
            const name = el.getAttribute('name') ? `[name="${el.getAttribute('name')}"]` : '';
            const placeholder = el.getAttribute('placeholder') ? `[placeholder="${el.getAttribute('placeholder')}"]` : '';
            const ariaLabel = el.getAttribute('aria-label') ? `[aria-label="${el.getAttribute('aria-label')}"]` : '';
            
            let attrs = [id, className, type, role, name, placeholder, ariaLabel].filter(Boolean).join(' ');
            result.push(`- [e${index}] <${tagName} ${attrs}> "${text.trim().substring(0, 50)}"`);
        });
        return result.join('\\n');
        """
        return page.execute_script(snapshot_js)

async def heal_selector(driver, failed_selector: str, action_type: str, framework: str = "playwright") -> str:
    """Uses the configured LLM provider to heal a failed selector by analyzing the layout snapshot."""
    token_efficient = os.environ.get("TOKEN_EFFICIENT_MODE", "true").lower() == "true"
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    
    # Extract snapshot based on framework
    if framework == "appium":
        print(f"[AWARSE Healer] Extracting native Appium XML page source layout...")
        layout_content = driver.page_source
        prompt = f"""
You are the self-healing engine of AWARSE (Autonomous Web-Automation Runtime Self-Healing Engine).
A mobile native Appium action '{action_type}' failed because the selector '{failed_selector}' could not be located.
The mobile UI structure has changed. Your task is to identify the corrected selector for the intended element.

Here is the XML layout tree of the current mobile screen:
```xml
{layout_content[:15000]}
```

Based on the old selector '{failed_selector}' and the current mobile layout, identify the intended target.
Provide a corrected XPath, ID, or Accessibility ID selector for that element.

Return ONLY a JSON object matching this structure:
{{
  "healed_selector": "working selector (e.g., '//android.widget.Button[@text=\"Submit\"]' or 'id/continue_btn')",
  "explanation": "Brief reasoning for selecting this element",
  "confidence": 0.0 to 1.0
}}
"""
    else:
        # Web-based (Playwright or Selenium)
        if token_efficient:
            print(f"[AWARSE Healer] Generating token-efficient Markdown snapshot...")
            snapshot_str = await generate_markdown_snapshot(driver)
            layout_details = f"```markdown\n{snapshot_str}\n```"
        else:
            print(f"[AWARSE Healer] Falling back to full HTML context...")
            if framework == "playwright":
                html_content = await driver.content()
            else:
                html_content = driver.page_source
            layout_details = f"```html\n{html_content[:10000]}\n```"
            
        prompt = f"""
You are the self-healing engine of AWARSE (Autonomous Web-Automation Runtime Self-Healing Engine).
A web interaction '{action_type}' failed because the selector '{failed_selector}' could not be located.
The structure of the web page has changed. Your task is to identify the new selector for the intended element.

Here is the layout representation of the current page:
{layout_details}

Based on the old selector '{failed_selector}' and the current page elements, identify the intended target.
Provide a corrected, working CSS selector or XPath for that element.

Return ONLY a JSON object matching this structure:
{{
  "healed_selector": "working selector (e.g., 'button.btn-primary' or 'input#email')",
  "explanation": "Brief reasoning for selecting this element",
  "confidence": 0.0 to 1.0
}}
"""
    
    print(f"[AWARSE Healer] Invoking LLM provider '{provider}' to heal selector...")
    
    if os.environ.get("AWARSE_MOCK_HEAL") == "true":
        print("[AWARSE Healer] MOCK MODE ACTIVE: Simulating LLM response.")
        if failed_selector == "#submit-btn":
            response_text = json.dumps({
                "healed_selector": "#healed-submit-action-button",
                "explanation": "Simulated healing for verification purposes in CI.",
                "confidence": 1.0
            })
        else:
            response_text = json.dumps({
                "healed_selector": failed_selector,
                "explanation": "Simulated healing (fallback).",
                "confidence": 1.0
            })
    elif provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment.")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        response_text = response.text
        
    elif provider in ("anthropic", "claude"):
        from anthropic import Anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment.")
        client = Anthropic(api_key=api_key)
        model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
        response = client.messages.create(
            model=model,
            max_tokens=1000,
            system="You are an expert web automation healer. You output ONLY valid JSON.",
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = response.content[0].text
        
    elif provider in ("openai", "copilot"):
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL", None)
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment.")
        client = OpenAI(api_key=api_key, base_url=base_url)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        response_text = response.choices[0].message.content
        
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
        
    try:
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        result = json.loads(clean_text)
        healed = result.get("healed_selector")
        print(f"[AWARSE Healer] HEALED: '{failed_selector}' -> '{healed}' (confidence: {result.get('confidence')})")
        print(f"[AWARSE Healer] REASON: {result.get('explanation')}")
        
        # Log to in-memory resources
        healed_logs.append({
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type,
            "failed_selector": failed_selector,
            "healed_selector": healed,
            "explanation": result.get("explanation"),
            "confidence": result.get("confidence")
        })
        
        # Dump to healed_logs.json file for the local dashboard to read
        try:
            server_dir = os.path.dirname(os.path.abspath(__file__))
            log_path = os.path.join(server_dir, "healed_logs.json")
            with open(log_path, "w") as f:
                json.dump(healed_logs, f, indent=2)
        except Exception as log_err:
            print(f"[AWARSE] Failed to write healed_logs.json: {log_err}")
        
        return healed
    except Exception as e:
        print(f"[AWARSE Healer] Failed to parse healer response: {e}. Raw response: {response_text}")
        raise

# --- ABSTRACT DRIVERS LAYER ---

class BaseDriver:
    async def navigate(self, url: str) -> str:
        raise NotImplementedError()
    async def click(self, selector: str) -> str:
        raise NotImplementedError()
    async def fill(self, selector: str, value: str) -> str:
        raise NotImplementedError()
    async def get_content(self) -> str:
        raise NotImplementedError()
    async def evaluate_js(self, script: str) -> str:
        raise NotImplementedError()
    async def take_screenshot(self, filename: str) -> str:
        raise NotImplementedError()
    async def get_snapshot(self) -> str:
        raise NotImplementedError()

class PlaywrightDriver(BaseDriver):
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def get_page(self):
        if self.page is None:
            print("[AWARSE] Launching Playwright headless browser...")
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
        return self.page

    async def navigate(self, url: str) -> str:
        page = await self.get_page()
        await page.goto(url)
        return f"Successfully navigated to {url} (Playwright)"

    async def click(self, selector: str) -> str:
        page = await self.get_page()
        try:
            await page.click(selector, timeout=3000)
            return f"Successfully clicked: {selector}"
        except Exception as e:
            print(f"[AWARSE] Click failed for '{selector}'. Healing...")
            healed = await heal_selector(page, selector, "click", "playwright")
            await page.click(healed, timeout=5000)
            return f"Clicked after healing. Healed '{selector}' to '{healed}'"

    async def fill(self, selector: str, value: str) -> str:
        page = await self.get_page()
        try:
            await page.fill(selector, value, timeout=3000)
            return f"Successfully filled: {selector}"
        except Exception as e:
            print(f"[AWARSE] Fill failed for '{selector}'. Healing...")
            healed = await heal_selector(page, selector, "fill", "playwright")
            await page.fill(healed, value, timeout=5000)
            return f"Filled after healing. Healed '{selector}' to '{healed}'"

    async def get_content(self) -> str:
        page = await self.get_page()
        return await page.evaluate("() => document.body.innerText")

    async def evaluate_js(self, script: str) -> str:
        page = await self.get_page()
        res = await page.evaluate(script)
        return f"JS evaluation returned: {res}"

    async def take_screenshot(self, filename: str) -> str:
        page = await self.get_page()
        filepath = os.path.abspath(filename)
        await page.screenshot(path=filepath)
        return f"Screenshot saved successfully to {filepath}"

    async def get_snapshot(self) -> str:
        page = await self.get_page()
        return await generate_markdown_snapshot(page)

class SeleniumDriver(BaseDriver):
    def __init__(self):
        self.driver = None

    def get_driver(self):
        if self.driver is None:
            print("[AWARSE] Launching Selenium headless Chrome...")
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            self.driver = webdriver.Chrome(options=options)
        return self.driver

    async def navigate(self, url: str) -> str:
        driver = self.get_driver()
        driver.get(url)
        return f"Successfully navigated to {url} (Selenium)"

    async def click(self, selector: str) -> str:
        driver = self.get_driver()
        from selenium.webdriver.common.by import By
        by = By.XPATH if selector.startswith("/") or selector.startswith("(") else By.CSS_SELECTOR
        try:
            element = driver.find_element(by, selector)
            element.click()
            return f"Successfully clicked: {selector}"
        except Exception as e:
            print(f"[AWARSE] Click failed for '{selector}'. Healing...")
            healed = await heal_selector(driver, selector, "click", "selenium")
            by_healed = By.XPATH if healed.startswith("/") or healed.startswith("(") else By.CSS_SELECTOR
            element = driver.find_element(by_healed, healed)
            element.click()
            return f"Clicked after healing. Healed '{selector}' to '{healed}'"

    async def fill(self, selector: str, value: str) -> str:
        driver = self.get_driver()
        from selenium.webdriver.common.by import By
        by = By.XPATH if selector.startswith("/") or selector.startswith("(") else By.CSS_SELECTOR
        try:
            element = driver.find_element(by, selector)
            element.clear()
            element.send_keys(value)
            return f"Successfully filled: {selector}"
        except Exception as e:
            print(f"[AWARSE] Fill failed for '{selector}'. Healing...")
            healed = await heal_selector(driver, selector, "fill", "selenium")
            by_healed = By.XPATH if healed.startswith("/") or healed.startswith("(") else By.CSS_SELECTOR
            element = driver.find_element(by_healed, healed)
            element.clear()
            element.send_keys(value)
            return f"Filled after healing. Healed '{selector}' to '{healed}'"

    async def get_content(self) -> str:
        driver = self.get_driver()
        return driver.find_element("css selector", "body").text

    async def evaluate_js(self, script: str) -> str:
        driver = self.get_driver()
        res = driver.execute_script(script)
        return f"JS evaluation returned: {res}"

    async def take_screenshot(self, filename: str) -> str:
        driver = self.get_driver()
        filepath = os.path.abspath(filename)
        driver.save_screenshot(filepath)
        return f"Screenshot saved successfully to {filepath}"

    async def get_snapshot(self) -> str:
        driver = self.get_driver()
        return await generate_markdown_snapshot(driver)

class AppiumDriver(BaseDriver):
    def __init__(self):
        self.driver = None

    def get_driver(self):
        if self.driver is None:
            print("[AWARSE] Connecting to Appium mobile automation server...")
            from appium import webdriver
            from appium.options.common import AppiumOptions
            
            server_url = os.environ.get("APPIUM_SERVER_URL", "http://localhost:4723")
            options = AppiumOptions()
            options.set_capability("platformName", os.environ.get("APPIUM_PLATFORM_NAME", "Android"))
            options.set_capability("automationName", os.environ.get("APPIUM_AUTOMATION_NAME", "UiAutomator2"))
            options.set_capability("deviceName", os.environ.get("APPIUM_DEVICE_NAME", "Android Emulator"))
            options.set_capability("app", os.environ.get("APPIUM_APP", ""))
            
            self.driver = webdriver.Remote(server_url, options=options)
        return self.driver

    async def navigate(self, url: str) -> str:
        # Navigate is usually deep linking or opening app activity in mobile
        driver = self.get_driver()
        driver.get(url)
        return f"Navigated app to: {url} (Appium)"

    async def click(self, selector: str) -> str:
        driver = self.get_driver()
        from selenium.webdriver.common.by import By
        by = By.XPATH if selector.startswith("/") or selector.startswith("(") else By.ID
        try:
            element = driver.find_element(by, selector)
            element.click()
            return f"Successfully tapped element: {selector}"
        except Exception as e:
            print(f"[AWARSE] Tap failed for '{selector}'. Healing...")
            healed = await heal_selector(driver, selector, "tap", "appium")
            by_healed = By.XPATH if healed.startswith("/") or healed.startswith("(") else By.ID
            element = driver.find_element(by_healed, healed)
            element.click()
            return f"Tapped element after healing. Healed '{selector}' to '{healed}'"

    async def fill(self, selector: str, value: str) -> str:
        driver = self.get_driver()
        from selenium.webdriver.common.by import By
        by = By.XPATH if selector.startswith("/") or selector.startswith("(") else By.ID
        try:
            element = driver.find_element(by, selector)
            element.send_keys(value)
            return f"Successfully sent keys to element: {selector}"
        except Exception as e:
            print(f"[AWARSE] Input failed for '{selector}'. Healing...")
            healed = await heal_selector(driver, selector, "input", "appium")
            by_healed = By.XPATH if healed.startswith("/") or healed.startswith("(") else By.ID
            element = driver.find_element(by_healed, healed)
            element.send_keys(value)
            return f"Sent keys after healing. Healed '{selector}' to '{healed}'"

    async def get_content(self) -> str:
        # Returns raw XML string in mobile view
        driver = self.get_driver()
        return driver.page_source

    async def evaluate_js(self, script: str) -> str:
        return "evaluate_js is not supported on mobile native platforms."

    async def take_screenshot(self, filename: str) -> str:
        driver = self.get_driver()
        filepath = os.path.abspath(filename)
        driver.save_screenshot(filepath)
        return f"Mobile screenshot saved to {filepath}"

    async def get_snapshot(self) -> str:
        # In Appium, layout snapshot is the raw page source XML hierarchy
        driver = self.get_driver()
        return driver.page_source

# Instantiate active driver based on env config
framework = os.environ.get("AUTOMATION_FRAMEWORK", "playwright").lower()

if framework == "playwright":
    driver_instance = PlaywrightDriver()
elif framework == "selenium":
    driver_instance = SeleniumDriver()
elif framework == "appium":
    driver_instance = AppiumDriver()
else:
    raise ValueError(f"Unsupported automation framework: {framework}")

# --- MCP TOOLS ---

@mcp.tool()
async def navigate(url: str) -> str:
    """Navigate the browser page or mobile app to a given URL."""
    return await driver_instance.navigate(url)

@mcp.tool()
async def click_element(selector: str) -> str:
    """Click/tap an element. Automatically heals the selector if it fails."""
    return await driver_instance.click(selector)

@mcp.tool()
async def fill_element(selector: str, value: str) -> str:
    """Fill a form/input element with a value. Automatically heals the selector if it fails."""
    return await driver_instance.fill(selector, value)

@mcp.tool()
async def get_content() -> str:
    """Retrieve the text content (web) or layout XML (mobile) of the current page/screen."""
    return await driver_instance.get_content()

@mcp.tool()
async def evaluate_js(script: str) -> str:
    """Evaluate a JavaScript string on the current web page (Supported on Web frameworks only)."""
    return await driver_instance.evaluate_js(script)

@mcp.tool()
async def take_screenshot(filename: str = "screenshot.png") -> str:
    """Take a screenshot of the current page/screen and save it locally."""
    return await driver_instance.take_screenshot(filename)

# --- RESOURCES ---

@mcp.resource("awarse://logs/healed-selectors")
def get_healed_logs() -> str:
    """Get the session log of all selectors successfully healed by AWARSE."""
    return json.dumps(healed_logs, indent=2)

@mcp.resource("awarse://page/dom")
async def get_page_dom() -> str:
    """Get the layout snapshot (Markdown elements map for web, XML for mobile) of the active page."""
    return await driver_instance.get_snapshot()

# --- PROMPTS ---

@mcp.prompt()
def diagnose_selector_failure(selector: str, action: str) -> str:
    """Create a diagnostic assistant prompt to analyze a failed web/mobile element action."""
    return f"""
Analyze the web/mobile automation failure for action '{action}' on selector '{selector}'.
First, review the healed selectors logs using the 'awarse://logs/healed-selectors' resource.
Then, output a clear summary detailing:
1. Why the original selector failed.
2. The healed selector that AWARSE successfully resolved.
3. Recommend how the user should update their codebase or test scripts to use the stable, repaired selector.
"""

@mcp.prompt()
def generate_playwright_test(url: str) -> str:
    """Create a prompt to generate a new Playwright test based on the active page layout."""
    return f"""
You are an expert QA and automation engineer.
Generate a complete, modern Playwright TypeScript test file that interacts with the page: '{url}'.

Use the 'awarse://page/dom' resource to view the structure of the page, locate the interactive elements, and identify the most stable, reliable selectors to write the automation steps.

Make sure the test script:
1. Navigates to the URL.
2. Interacts with the elements cleanly.
3. Includes solid assertions.
"""

if __name__ == "__main__":
    # Start the FastMCP server
    mcp.run()
