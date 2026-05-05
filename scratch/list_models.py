import os
from google import genai

client = genai.Client(api_key=os.getenv("googlekey"))
for model in client.models.list():
    if "embed" in model.name:
        print(f"Name: {model.name}, Supported Methods: {model.supported_variants}")
