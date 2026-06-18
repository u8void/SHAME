import os
import sys

# Setup Open Interpreter exactly as in controller.py
try:
    from interpreter import interpreter as _oi
    _oi.auto_run = True
    _oi.verbose = True
    _oi.max_output = 4000
    _oi.offline = True
    _oi.sync_computer = False
    _oi.loop = False
    _oi.llm.supports_functions = False
    _oi.llm.supports_vision = False
    _oi.llm.api_base = os.environ.get("IRIS_OI_API_BASE", "http://localhost:11434")
    _oi.llm.model = os.environ.get("IRIS_OI_MODEL", "ollama/mistral")
    _oi.system_message = "Test message."
    
    print("OI initialization successful.")
except Exception as e:
    print(f"Init error: {e}")
    sys.exit(1)

try:
    print("Running task...")
    for chunk in _oi.chat("echo 'hello'", display=False, stream=True, blocking=True):
        print(chunk)
except Exception as e:
    print(f"Chat error: {e}")
