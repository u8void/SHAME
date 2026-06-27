import sys, os
sys.path.append(os.getcwd())
from src.iris import load_model, ModelRole
from src.controller import _get_agent_system_prompt

llm = load_model(ModelRole.CONTROL)
control_messages = [
    {"role": "system", "content": _get_agent_system_prompt()},
    {"role": "user", "content": "set brightness to 20%"}
]

print("Starting generation...")
res = ""
for chunk in llm.create_chat_completion(messages=control_messages, max_tokens=200, stream=True, temperature=0.1):
    delta = chunk["choices"][0].get("delta", {})
    if "content" in delta:
        c = delta["content"]
        res += c
        print(c, end="", flush=True)
print("\nFinal output:", repr(res))
