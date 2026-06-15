import asyncio
import os
import dotenv
from google.antigravity import Agent, LocalAgentConfig, types

# Load API keys and secrets from .env file
dotenv.load_dotenv()

async def run_self_healing_automation():
    print("[INFO] Starting AWARSE Self-Healing Web Automation Example...")
    
    # 1. Define the AWARSE MCP Server configuration
    # The agent will launch and manage this server during the session lifecycle
    mcp_servers = [
        types.McpStdioServer(
            name="awarse",
            command="venv/bin/python",
            args=["self_healing_server.py"],
            env={
                "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY")
            }
        )
    ]
    
    # 2. Configure the Antigravity Agent
    # We equip the agent with the AWARSE server so it has self-healing tools
    config = LocalAgentConfig(
        model_name="gemini-1.5-flash",
        mcp_servers=mcp_servers
    )
    
    # Locate our local test HTML page
    test_page_path = os.path.abspath("test_page.html")
    test_page_url = f"file://{test_page_path}"
    
    async with Agent(config) as agent:
        print("[AGENT] Initialized and connected to AWARSE MCP server.")
        
        # Action 1: Navigate to the login/submission page
        print(f"[AGENT] Directing agent to navigate to: {test_page_url}")
        res = await agent.chat(f"Go to '{test_page_url}'")
        print(f"[AGENT RESPONSE]:\n{await res.text()}\n")
        
        # Action 2: Enter credentials into the inputs
        print("[AGENT] Directing agent to fill in form details...")
        res = await agent.chat("Fill the username input with 'dev_user' and the email with 'dev@example.com'.")
        print(f"[AGENT RESPONSE]:\n{await res.text()}\n")
        
        # Action 3: Dynamically break the selector using JS
        # This simulates a website redesign happening in the background or between test runs
        print("[AGENT] Simulating a site layout update that breaks the button selector...")
        res = await agent.chat("Run JavaScript 'mutateDOM()' on the page to trigger layout changes.")
        print(f"[AGENT RESPONSE]:\n{await res.text()}\n")
        
        # Action 4: Instruct the agent to click the original, now-broken button selector
        # AWARSE will intercept the failure, invoke Gemini, find the new button, and click it successfully
        print("[AGENT] Directing agent to submit the form using the old selector '#submit-btn'...")
        res = await agent.chat("Click the element with selector '#submit-btn'")
        print(f"[AGENT RESPONSE]:\n{await res.text()}\n")
        
        # Action 5: Confirm success and capture the final submission screen
        print("[AGENT] Verifying successful submission...")
        res = await agent.chat("Verify that the form was submitted successfully and take a screenshot named 'success_log.png'.")
        print(f"[AGENT RESPONSE]:\n{await res.text()}\n")

if __name__ == "__main__":
    # Ensure GEMINI_API_KEY is available
    if not os.environ.get("GEMINI_API_KEY"):
        print("[ERROR] GEMINI_API_KEY is not set in your .env file.")
    else:
        asyncio.run(run_self_healing_automation())
