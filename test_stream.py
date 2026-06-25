from src.iris import _stream_tokens, ModelRole, TaskType

messages = [{"role": "user", "content": "talk about the giza pyramids"}]
for ev in _stream_tokens(ModelRole.GENERAL, messages, max_tokens=200):
    if ev["type"] == "token":
        print(ev["content"], end="", flush=True)
print()
