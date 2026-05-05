import os
import asyncio
from google import genai
from dotenv import load_dotenv

load_dotenv()

async def main():
    client = genai.Client(api_key=os.getenv("googlekey"))
    print("Listing models...")
    try:
        # The new SDK might use client.models.list()
        for model in client.models.list():
            print(f"Model: {model.name}, Supported Actions: {model.supported_actions}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
