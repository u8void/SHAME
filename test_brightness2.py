import sys
sys.path.insert(0, '/run/media/hamdy/Hamdy/IRIS/IRIS/iris-Ai')
from src.iris_engine import ModelRole, load_model
from src.iris_control import get_control_prompt
from src.controller import _get_agent_system_prompt

control_llm = load_model(ModelRole.CONTROL)
control_messages = [{"role": "system", "content": _get_agent_system_prompt()}]
control_messages.append({"role": "user", "content": "set brightness to 10%\n\n[SYSTEM REMINDER: You MUST output a valid JSON object for the action. Do not reply in plain text.]"})
action_json = ""
for chunk in control_llm.create_chat_completion(messages=control_messages, max_tokens=1024, stream=True, temperature=0.1):
    delta = chunk["choices"][0].get("delta", {})
    if "content" in delta:
        action_json += delta["content"]
print("RAW OUTPUT:", repr(action_json))
