import os
import sys

try:
    from interpreter import interpreter as _oi
    _oi.auto_run = True
    _oi.verbose = True
    _oi.offline = True
    _oi.sync_computer = False
    _oi.loop = False
    
    # Point to the native gguf
    model_path = os.path.abspath(os.path.join(os.getcwd(), "models", "iris_004.gguf"))
    print(f"Loading native GGUF: {model_path}")
    
    _oi.llm.api_base = None
    _oi.llm.model = model_path
    
    print("OI initialized. Sending test chat...")
    for chunk in _oi.chat("echo 'hello'", display=False, stream=True, blocking=True):
        print(chunk)
except Exception as e:
    print(f"Error: {e}")
