from interpreter import interpreter

def my_custom_llm(*args, **kwargs):
    print("Intercepted kwargs:", kwargs)
    yield "print('hello from custom llm')\n"

try:
    interpreter.llm.completions = my_custom_llm
    print("Testing custom LLM 2...")
    for chunk in interpreter.chat("Write a python script to say hello", display=False, stream=True):
        print(chunk)
except Exception as e:
    print(f"Error: {e}")
