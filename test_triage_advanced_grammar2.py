import sys, os, json
sys.path.append(os.getcwd())
from src.iris import load_model, ModelRole

llm = load_model(ModelRole.TRIAGE)

triage_prompt = """You are the Iris AI Router. Output exactly ONE JSON object.

Route Categories:
- SEARCH: Factual questions, current events, history, people.
- REASONING: Explanations, logic, recipes, counting letters.
- GENERAL: Casual chat, opinions, identity.
- MATH: Math problems.
- CODE_SIMPLE: Single functions, HTML, canvas.
- CODE_COMPLEX: Full projects.
- CONTROL: System commands, apps, brightness, browser automation.
- GREETING: Simple greetings like "hello", "hi", "hey".
"""

def test_query(q):
    triage_messages = [
        {"role": "system", "content": triage_prompt},
        {"role": "user", "content": q}
    ]

    res = llm.create_chat_completion(
        messages=triage_messages, 
        max_tokens=100, 
        temperature=0.1,
        response_format={
            "type": "json_object",
            "schema": {
                "type": "object",
                "properties": {
                    "route": {
                        "type": "string", 
                        "enum": ["SEARCH", "REASONING", "GENERAL", "MATH", "CODE_SIMPLE", "CODE_COMPLEX", "CONTROL", "GREETING"]
                    },
                    "search_keywords": {
                        "type": "string"
                    },
                    "greeting_response": {
                        "type": "string"
                    }
                },
                "required": ["route"]
            }
        }
    )
    print(f"\nQuery: {q}")
    print("Output:", res["choices"][0]["message"]["content"])

test_query("hello")
test_query("what is the capital of france?")
test_query("my ram is full what is that")
test_query("set brightness to 20%")
