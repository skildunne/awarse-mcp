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

async def generate_markdown_snapshot(page) -> str:
    """Generates a highly token-efficient markdown representation of interactive elements, similar to playwright-cli."""
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
            const type = el.type ? `[type="${el.type}"]` : '';
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

async def heal_selector(page, failed_selector: str, action_type: str) -> str:
    """Uses the configured LLM provider to heal a failed selector by analyzing the DOM state."""
    # Check if token-efficient mode is enabled (default is True)
    token_efficient = os.environ.get("TOKEN_EFFICIENT_MODE", "true").lower() == "true"
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    
    if token_efficient:
        print(f"[AWARSE Healer] Generating token-efficient Markdown snapshot...")
        snapshot_str = await generate_markdown_snapshot(page)
        prompt = f"""
You are the self-healing engine of AWARSE (Autonomous Web-Automation Runtime Self-Healing Engine).
A web interaction '{action_type}' failed because the selector '{failed_selector}' could not be located.
The structure of the web page has changed. Your task is to identify the new selector for the intended element.

Here is a token-efficient interactive element map of the current page layout:
```markdown
{snapshot_str}
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
    else:
        # Fallback to full HTML context and JSON DOM snapshot
        print(f"[AWARSE Healer] Falling back to full HTML context...")
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
        html_content = await page.content()
        dom_str = json.dumps(dom_snapshot, indent=2)
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
    
    print(f"[AWARSE Healer] Invoking LLM provider '{provider}' to heal selector...")
    
    if provider == "gemini":
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

# --- RESOURCES ---

@mcp.resource("awarse://logs/healed-selectors")
def get_healed_logs() -> str:
    """Get the session log of all selectors successfully healed by AWARSE."""
    return json.dumps(healed_logs, indent=2)

@mcp.resource("awarse://page/dom")
async def get_page_dom() -> str:
    """Get the token-efficient Markdown snapshot of the active page layout."""
    page = await browser_manager.get_page()
    if page:
        return await generate_markdown_snapshot(page)
    return "No active page loaded."

# --- PROMPTS ---

@mcp.prompt()
def diagnose_selector_failure(selector: str, action: str) -> str:
    """Create a diagnostic assistant prompt to analyze a failed web element action."""
    return f"""
Analyze the web automation failure for action '{action}' on selector '{selector}'.
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
