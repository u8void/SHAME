from interpreter import interpreter

def my_custom_llm(messages):
    print("Intercepted messages:", messages)
    yield "print('hello from custom llm')\n"

try:
    interpreter.llm.completions = my_custom_llm
    print("Testing custom LLM...")
    for chunk in interpreter.chat("Write a python script to say hello", display=False, stream=True):
        pass
except Exception as e:
    print(f"Error: {e}")
