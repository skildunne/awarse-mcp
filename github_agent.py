import asyncio
import os
import dotenv
from google.antigravity import Agent, LocalAgentConfig, types

# Load variables from .env
dotenv.load_dotenv()

async def main():
    mcp_servers = [
        types.McpStdioServer(
            name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={
                "GITHUB_PERSONAL_ACCESS_TOKEN": os.environ.get("GITHUB_PAT")
            }
        )
    ]
    
    config = LocalAgentConfig(
        model_name="gemini-1.5-flash",
        mcp_servers=mcp_servers
    )
    
    async with Agent(config) as agent:
        print("[AGENT] Initializing connection to GitHub MCP...")
        response = await agent.chat("Search for repositories under my account 'skildunne' and list the first 3.")
        print(f"\n[AGENT RESPONSE]:\n{await response.text()}")

if __name__ == "__main__":
    asyncio.run(main())
