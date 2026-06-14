import asyncio
import dotenv
from google.antigravity import Agent, LocalAgentConfig

dotenv.load_dotenv()

async def main():
    # Config setup
    # If GEMINI_API_KEY env is not set, you can provide the api_key parameter:
    # config = LocalAgentConfig(model_name="gemini-1.5-flash", api_key="YOUR_API_KEY")
    config = LocalAgentConfig(model_name="gemini-1.5-flash")
    
    async with Agent(config) as agent:
        response = await agent.chat("Hello! Explain gravity in one sentence.")
        print(await response.text())

if __name__ == "__main__":
    asyncio.run(main())
