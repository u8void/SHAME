import json
from src.iris_engine import _model_pool, ModelRole, load_model, _model_paths
from llama_cpp import Llama

with open("last_request.json", "r") as f:
    data = json.load(f)

path = _model_paths.get(ModelRole.CODE)
if not path:
    load_model(ModelRole.CODE, override_n_ctx=16384)
    path = _model_paths.get(ModelRole.CODE)

llm = Llama(
    model_path=path,
    n_gpu_layers=-1,
    n_ctx=16384,
    n_batch=1024,
    verbose=True
)

valid_msgs = []
for m in data.get("messages", data.get("input", [])):
    if m.get("role") in ["system", "user", "assistant"]:
        valid_msgs.append(m)

print("Running with tools...")
try:
    generator = llm.create_chat_completion(
        messages=valid_msgs,
        tools=data.get("tools"),
        stream=True,
        temperature=0.2,
        max_tokens=200
    )
    for chunk in generator:
        print(chunk)
except Exception as e:
    print("CRASH:", e)
