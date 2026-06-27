import sys
from src.iris import load_model, ModelRole, _system_prompt_for

llm = load_model(ModelRole.GENERAL)
sys_prompt = _system_prompt_for(ModelRole.GENERAL)
messages = [
    {"role": "system", "content": sys_prompt + "\n\n[SYSTEM DIRECTIVE: The current local system time is Saturday, June 27, 2026, 14:39:54 UTC+03:00.]"},
    {"role": "user", "content": "what time is it in germany"},
    {"role": "assistant", "content": "<think>\n"}
]
res = llm.create_chat_completion(messages=messages, max_tokens=200)
print("REPLY:", repr(res["choices"][0]["message"]["content"]))
