import asyncio
import os
import dotenv
from google.antigravity import Agent, LocalAgentConfig, types

# Load .env variables
dotenv.load_dotenv()

async def main():
    # Setup AWARSE MCP server as local stdio server
    mcp_servers = [
        types.McpStdioServer(
            name="awarse",
            command="venv/bin/python",
            args=["self_healing_server.py"]
        )
    ]
    
    # Configure the Agent to use AWARSE
    config = LocalAgentConfig(
        model_name="gemini-1.5-flash",
        mcp_servers=mcp_servers
    )
    
    print("[CLIENT] Launching Antigravity Agent with AWARSE self-healing MCP server...")
    
    async with Agent(config) as agent:
        test_page_path = os.path.abspath("test_page.html")
        test_page_url = f"file://{test_page_path}"
        
        # 1. Navigate to mock page
        print(f"[CLIENT] Navigating to: {test_page_url}")
        res = await agent.chat(f"Navigate to '{test_page_url}'")
        print(f"[AGENT] {await res.text()}")
        
        # 2. Fill form fields
        print("[CLIENT] Filling form fields...")
        res = await agent.chat("Fill in username as 'healer_test' and email as 'healer@test.local'.")
        print(f"[AGENT] {await res.text()}")
        
        # 3. Simulate UI redesign / DOM mutation
        print("[CLIENT] Simulating UI redesign via JS evaluation...")
        res = await agent.chat("Evaluate JavaScript 'mutateDOM()'")
        print(f"[AGENT] {await res.text()}")
        
        # 4. Attempt to click original selector (which is now broken)
        print("[CLIENT] Instructing agent to click original button (#submit-btn)...")
        res = await agent.chat("Click the element with selector '#submit-btn'")
        print(f"[AGENT] {await res.text()}")
        
        # 5. Check if form submission succeeded
        print("[CLIENT] Verifying page text content...")
        res = await agent.chat("Get page text content and print it.")
        print(f"[AGENT] {await res.text()}")
        
        # 6. Capture screenshot of final state
        print("[CLIENT] Capturing screenshot of final state...")
        res = await agent.chat("Take a screenshot and save it as 'healed_submission.png'")
        print(f"[AGENT] {await res.text()}")

if __name__ == "__main__":
    asyncio.run(main())
