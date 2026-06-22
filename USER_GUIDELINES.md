# AWARSE User & Configuration Guidelines

This document provides detailed guidelines on configuring the **Autonomous Web-Automation Runtime Self-Healing Engine (AWARSE)** for different Large Language Model (LLM) providers and web/mobile automation frameworks.

---

## 📋 Compatibility Matrix

AWARSE is built on a modular driver architecture and LLM routing layer. The table below shows the support matrix:

| Framework | Gemini (Default) | Claude (Anthropic) | OpenAI / Copilot | Local LLMs (Ollama/vLLM) |
| :--- | :---: | :---: | :---: | :---: |
| **Playwright** (Web) |  (Stable) |  (Stable) |  (Stable) |  (Supported) |
| **Selenium** (Web) |  (Stable) |  (Stable) |  (Stable) |  (Supported) |
| **Appium** (Mobile) |  (Stable) |  (Stable) |  (Stable) |  (Supported) |

---

## 🤖 Configuring LLM Providers

AWARSE uses the `LLM_PROVIDER` environment variable to determine which client libraries and API endpoints to call when self-healing. Add these configurations to your `.env` file or export them in your terminal.

### 1. Google Gemini (Default)
Recommended model: `gemini-2.5-flash` (fast, highly accurate at locating visual structure, very cost-effective).

**Configuration Variables:**
```env
LLM_PROVIDER="gemini"
GEMINI_API_KEY="your-gemini-api-key"
GEMINI_MODEL="gemini-2.5-flash"  # Optional: defaults to gemini-2.5-flash
```

### 2. Claude (Anthropic)
Recommended model: `claude-3-5-haiku-latest` or `claude-3-5-sonnet-latest`.

**Configuration Variables:**
```env
LLM_PROVIDER="claude"  # Or "anthropic"
ANTHROPIC_API_KEY="your-anthropic-api-key"
ANTHROPIC_MODEL="claude-3-5-haiku-latest"  # Optional: defaults to claude-3-5-haiku-latest
```

### 3. OpenAI / Copilot
Recommended model: `gpt-4o-mini` (excellent JSON outputs) or `gpt-4o`.

**Configuration Variables:**
```env
LLM_PROVIDER="openai"
OPENAI_API_KEY="your-openai-api-key"
OPENAI_MODEL="gpt-4o-mini"  # Optional: defaults to gpt-4o-mini
```

### 4. Local Models (Ollama, vLLM, Private Endpoints)
You can point the OpenAI driver to a local or private OpenAI-compatible endpoint.

**Configuration Variables (Ollama Example):**
```env
LLM_PROVIDER="openai"
OPENAI_API_KEY="ollama"  # Ollama requires any non-empty string
OPENAI_BASE_URL="http://localhost:11434/v1"
OPENAI_MODEL="llama3"  # Replace with your loaded Ollama model
```

---

## ⚙️ Configuring Automation Frameworks

AWARSE abstracts the browser or device operations behind a driver class. Swap the driver using the `AUTOMATION_FRAMEWORK` variable.

### 1. Playwright (Web - Asynchronous)
The default and recommended web automation framework. Fast, headless by default, and supports modern web APIs.

* **Dependencies:**
  ```bash
  venv/bin/pip install playwright
  venv/bin/playwright install chromium
  ```
* **Variables:**
  ```env
  AUTOMATION_FRAMEWORK="playwright"
  ```

### 2. Selenium WebDriver (Web - Synchronous)
Ideal for integrating with legacy test suites or corporate Selenium grids.

* **Dependencies:**
  ```bash
  venv/bin/pip install selenium
  ```
* **Variables:**
  ```env
  AUTOMATION_FRAMEWORK="selenium"
  ```
* **Driver Lifecycle:** AWARSE launches a headless Chrome instance automatically using WebDriver manager defaults. Ensure Google Chrome is installed on the host machine.

### 3. Appium (Mobile Native / Hybrid)
Used for Android or iOS app self-healing. AWARSE extracts the XML source layout structure instead of HTML DOM maps to heal selectors.

* **Dependencies:**
  ```bash
  venv/bin/pip install Appium-Python-Client
  ```
* **Variables:**
  ```env
  AUTOMATION_FRAMEWORK="appium"
  APPIUM_SERVER_URL="http://localhost:4723"
  APPIUM_PLATFORM_NAME="Android" # "Android" or "iOS"
  APPIUM_DEVICE_NAME="Android Emulator"
  APPIUM_APP="/absolute/path/to/your/app.apk"
  ```
* **Driver Lifecycle:** Appium requires a running Appium server instance on the target host (typically port `4723`) and a configured device or emulator.

---

## ⚡ Unified Configuration Recipes (.env Profiles)

Choose a recipe, create/edit the `.env` file in the project root, and run `verify_healing.py` or startup the server:

### Recipe A: The Modern Stack (Playwright + Gemini)
*Best for fast, reliable, low-cost web automation.*

```env
# Framework config
AUTOMATION_FRAMEWORK="playwright"

# LLM config
LLM_PROVIDER="gemini"
GEMINI_API_KEY="AIzaSy..."
GEMINI_MODEL="gemini-2.5-flash"

# Opt-in settings
TOKEN_EFFICIENT_MODE="true"
```

### Recipe B: The Corporate Legacy Stack (Selenium + Claude)
*Best for existing enterprise test scripts running on Chrome.*

```env
# Framework config
AUTOMATION_FRAMEWORK="selenium"

# LLM config
LLM_PROVIDER="claude"
ANTHROPIC_API_KEY="sk-ant-..."
ANTHROPIC_MODEL="claude-3-5-haiku-latest"

# Opt-in settings
TOKEN_EFFICIENT_MODE="true"
```

### Recipe C: Mobile native testing (Appium + OpenAI)
*Best for mobile apps where element IDs change across builds.*

```env
# Framework config
AUTOMATION_FRAMEWORK="appium"
APPIUM_SERVER_URL="http://127.0.0.1:4723"
APPIUM_PLATFORM_NAME="Android"
APPIUM_DEVICE_NAME="Pixel_5_Emulator"
APPIUM_APP="/home/user/apps/production-build.apk"

# LLM config
LLM_PROVIDER="openai"
OPENAI_API_KEY="sk-proj-..."
OPENAI_MODEL="gpt-4o-mini"
```

---

## 🔍 Fine-Tuning Snapshot Performance

AWARSE supports two layout representation modes for web drivers:

1. **Token-Efficient Mode (`TOKEN_EFFICIENT_MODE="true"`) [Default]:**
   - Automatically executes a Javascript query inside the browser viewport.
   - Extracts all interactive tags (`<button>`, `<input>`, `<a>`, `[role="button"]`, etc.).
   - Builds a clean, numbered Markdown map (e.g. `- [e12] <button id="#submit"> "Sign In"`).
   - **Benefit:** Consumes under 1,000 tokens (reducing costs by **80%-90%** and accelerating LLM responses).
2. **Raw HTML Mode (`TOKEN_EFFICIENT_MODE="false"`):**
   - Extracts the raw outer HTML body (truncated to 10k characters).
   - **Benefit:** Gives the LLM complete CSS grid and style context, useful for highly styling-dependent layout changes.

---

## 🛠️ Troubleshooting & Diagnostics

* **Selenium ImportErrors:**
  If you configure `AUTOMATION_FRAMEWORK="selenium"`, ensure you run `venv/bin/pip install selenium`. The dependencies are dynamically imported to ensure users who only run Playwright don't require heavy Selenium or Appium client libraries.
* **Appium Session Creation Failures:**
  Ensure the Appium server is running (`appium` in terminal) and that the emulator/device is connected (`adb devices` matches the device capability).
* **Missing API Key Errors:**
  If AWARSE complains about missing credentials, verify that the `.env` file is in the root directory from which the MCP server is launched. When running inside visual editors (like Cursor or Claude Desktop), configure the environment variables directly inside the editor's `mcp_config.json` block:
  ```json
  "env": {
    "LLM_PROVIDER": "gemini",
    "GEMINI_API_KEY": "AIzaSy..."
  }
  ```
