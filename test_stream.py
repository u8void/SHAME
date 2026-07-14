import sys
from src.iris import ask_stream
from src.iris_engine import TaskType

for ev in ask_stream("cosx + sinx", [], None, {"user_lang": "English"}, force_role="math"):
    if ev["type"] == "token":
        sys.stdout.write(ev["content"])
    else:
        print("\nEVENT:", ev)
