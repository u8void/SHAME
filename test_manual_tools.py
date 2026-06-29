import json
from src.iris_engine import _model_pool, ModelRole, load_model, _model_paths
from llama_cpp import Llama
from api import extract_text

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
    verbose=False
)

tools = data.get("tools", [])

# Manually construct the system prompt with tools
system_content = ""
for m in data.get("messages", data.get("input", [])):
    if m.get("role") == "system":
        system_content += extract_text(m.get("content", "")) + "\n\n"

if tools:
    system_content += "# Tools\n\nYou may call one or more functions to assist with the user query.\n\nYou are provided with function signatures within <tools></tools> XML tags:\n<tools>\n"
    for tool in tools:
        system_content += json.dumps(tool) + "\n"
    system_content += "</tools>\n\nFor each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:\n<tool_call>\n{\"name\": <function-name>, \"arguments\": <args-json-object>}\n</tool_call>\n"

valid_msgs = [{"role": "system", "content": system_content}]
for m in data.get("messages", data.get("input", [])):
    if m.get("role") in ["user", "assistant"]:
        valid_msgs.append({
            "role": m.get("role"),
            "content": extract_text(m.get("content", ""))
        })

print("Running with manual tools injection...")
try:
    generator = llm.create_chat_completion(
        messages=valid_msgs,
        stream=True,
        temperature=0.2,
        max_tokens=200
    )
    for chunk in generator:
        delta = chunk["choices"][0]["delta"]
        if "content" in delta:
            print(delta["content"], end="", flush=True)
except Exception as e:
    print("\nCRASH:", e)
print("\nDone")
