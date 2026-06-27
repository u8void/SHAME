import sys, os
sys.path.append(os.getcwd())
from src.iris import load_model, ModelRole

llm = load_model(ModelRole.TRIAGE)

triage_prompt = """You are the Iris AI Router. Your ONLY job is to output ONE routing tag.

# Routing Categories
1. [ROUTE: SEARCH: keywords]
2. [ROUTE: REASONING]
3. [ROUTE: GENERAL]
4. [ROUTE: MATH]
5. [ROUTE: CODE_SIMPLE]
6. [ROUTE: CODE_COMPLEX]
7. [ROUTE: CONTROL]

# Final Instruction
You MUST ALWAYS start your response with a <think> block analyzing the user's intent, followed immediately by exactly one routing tag."""

triage_messages = [
    {"role": "system", "content": triage_prompt},
    {"role": "user", "content": "my ram is full what is that"}
]

res = ""
for chunk in llm.create_chat_completion(messages=triage_messages, max_tokens=100, stream=True, temperature=0.1):
    if "content" in chunk["choices"][0].get("delta", {}):
        res += chunk["choices"][0]["delta"]["content"]
print("\nModel Output:")
print(repr(res))
