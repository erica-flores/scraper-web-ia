from llm.llm_client import LLMClient
from google import genai
import os
from dotenv import load_dotenv
load_dotenv()

key = os.getenv("GEMINI_API_KEY", "")
client_raw = genai.Client(api_key=key)

models = ["gemini-2.0-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-2.5-flash"]

print("Testing each model individually:\n")
for model in models:
    try:
        resp = client_raw.models.generate_content(model=model, contents='Return the word "OK"')
        print(f"  OK  {model}: {resp.text.strip()[:40]}")
    except Exception as e:
        print(f"  FAIL {model}: {str(e)[:80]}")

print("\nNow testing LLMClient with fallback chain:")
try:
    c = LLMClient()
    r = c.extract_json('Return {"status": "ok", "value": 42}')
    print("SUCCESS:", r)
except Exception as e:
    print("FAILED:", e)
