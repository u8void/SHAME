import sys, os
sys.path.append(os.getcwd())
from src.iris import load_model, ModelRole

path = os.path.join(os.path.dirname(__file__), "documentations", "triage_routing_guide.md")
with open(path, "r", encoding="utf-8") as f:
    text = f.read().strip()

llm = load_model(ModelRole.TRIAGE)

triage_prompt = (
    "You are the Iris Routing Core.\n"
    "Your ONLY job is to output exactly ONE tag based on the user's request.\n"
    "Do NOT answer the user's question. Do NOT explain. ONLY output the tag.\n\n"
    f"Refer to these guidelines:\n\n{text}\n\n"
    "If you want to just chat or say hello, just reply normally."
)

triage_query = 'Query: "set brightness to 20%"\nOutput:'

triage_messages = [
    {"role": "system", "content": triage_prompt},
    {"role": "user", "content": triage_query}
]

res = ""
for chunk in llm.create_chat_completion(messages=triage_messages, max_tokens=64, stream=True, temperature=0.1):
    if "content" in chunk["choices"][0].get("delta", {}):
        res += chunk["choices"][0]["delta"]["content"]
print("\nModel Output:")
print(repr(res))
