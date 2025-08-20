# app/services/groq_client.py
import os
from dotenv import load_dotenv
load_dotenv()

from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not provided in environment")

# Synchronous client (we will call it from a background thread to avoid blocking FastAPI event loop)
client = Groq(api_key=GROQ_API_KEY)

# If you prefer an async client, you can import AsyncGroq:
# from groq import AsyncGroq
# async_client = AsyncGroq(api_key=GROQ_API_KEY)
