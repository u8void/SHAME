import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.iris import load_model, ModelRole

llm = load_model(ModelRole.REASONING)
messages = [{"role": "user", "content": "What is the capital of France? Think step by step."}]
stream = llm.create_chat_completion(messages=messages, stream=True, max_tokens=200)

full = ""
for chunk in stream:
    token = chunk["choices"][0].get("delta", {}).get("content", "")
    full += token
    print(token, end="", flush=True)
print("\n")
