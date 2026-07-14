from src.iris_engine import ModelRole, _stream_tokens
messages = [{"role": "user", "content": "2+2"}]
tokens = []
for ev in _stream_tokens(ModelRole.MATH, messages, max_tokens=100, temperature=0.2, think_mode="show"):
    if ev["type"] in ("token", "thinking"):
        tokens.append(ev["content"])
print("".join(tokens))
