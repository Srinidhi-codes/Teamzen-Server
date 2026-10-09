import asyncio
import os
import sys
from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig

async def main():
    issue_title = os.environ.get("ISSUE_TITLE", "")
    issue_body = os.environ.get("ISSUE_BODY", "")
    
    # Define what the agent is allowed to do
    config = LocalAgentConfig(
        system_instructions=(
            "You are an autonomous AI software engineer powered by Antigravity. "
            "You are running in a CI pipeline to fix a GitHub issue. "
            "You have full access to the codebase. "
            "Your goal is to find the relevant files, modify them to fix the issue, and then stop."
        ),
        # CapabilitiesConfig() enables write access (like editing files and running safe commands)
        capabilities=CapabilitiesConfig() 
    )

    prompt = f"""
    Please fix the following GitHub issue in the repository:
    
    Issue Title: {issue_title}
    
    Issue Description:
    {issue_body}
    
    Instructions:
    1. Read the necessary files to understand the context.
    2. Make the required edits using your file-editing tools.
    3. When you are done, summarize what you changed and finish your task.
    """

    print("Spawning Antigravity Agent...")
    
    # Start the agent using the SDK
    async with Agent(config) as agent:
        response = await agent.chat(prompt)
        
        # Stream the agent's thoughts and actions to the GitHub Actions console
        async for token in response:
            sys.stdout.write(token)
            sys.stdout.flush()
        print("\nAgent finished processing.")

if __name__ == "__main__":
    asyncio.run(main())
