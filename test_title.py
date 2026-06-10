from src.iris import load_model, ModelRole, _keep_loaded, unload_model
llm = load_model(ModelRole.TRIAGE)
messages = [
    {"role": "system", "content": "You are a helpful assistant. Provide a very short, concise title (2 to 4 words) for the user's query. DO NOT use quotes around the title. Just output the title."},
    {"role": "user", "content": "ok why do ai requires so much computing power"}
]
res = llm.create_chat_completion(messages=messages, max_tokens=150, temperature=0.3)
raw = res["choices"][0]["message"]["content"]
import re
title = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip().strip("\"'")
title_unclosed = re.sub(r'<think>.*', '', title, flags=re.DOTALL).strip()
print(f"RAW: {raw}")
print(f"TITLE: {title}")
print(f"TITLE_UNCLOSED: {title_unclosed}")
