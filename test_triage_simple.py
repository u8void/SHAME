import sys, os
sys.path.append(os.getcwd())
from src.iris import load_model, ModelRole

llm = load_model(ModelRole.TRIAGE)

def test(q):
    messages = [
        {"role": "system", "content": "You are a router. Output exactly one tag from: [SEARCH], [REASONING], [GENERAL], [MATH], [CODE_SIMPLE], [CODE_COMPLEX], [CONTROL].\n\nExamples:\nUser: hello\nRouter: [GENERAL]\n\nUser: what is capital of france\nRouter: [SEARCH]\n\nUser: set brightness to 20\nRouter: [CONTROL]"},
        {"role": "user", "content": q}
    ]
    res = llm.create_chat_completion(messages=messages, max_tokens=10, temperature=0.1)
    print(q, "->", res["choices"][0]["message"]["content"])

test("hello")
test("what is the capital of france?")
test("my ram is full what is that")
test("set brightness to 40%")
