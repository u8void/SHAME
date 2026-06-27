import sys, os, json
sys.path.append(os.getcwd())
from src.iris import load_model, ModelRole

llm = load_model(ModelRole.TRIAGE)

triage_prompt = """You are the Iris AI Router. Your ONLY job is to output ONE routing tag in a JSON object.

# Routing Categories
1. [ROUTE: SEARCH: keywords]
2. [ROUTE: REASONING]
3. [ROUTE: GENERAL]
4. [ROUTE: MATH]
5. [ROUTE: CODE_SIMPLE]
6. [ROUTE: CODE_COMPLEX]
7. [ROUTE: CONTROL]
"""

triage_messages = [
    {"role": "system", "content": triage_prompt},
    {"role": "user", "content": "my ram is full what is that"}
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
                "tag": {"type": "string", "enum": ["[ROUTE: SEARCH]", "[ROUTE: REASONING]", "[ROUTE: GENERAL]", "[ROUTE: MATH]", "[ROUTE: CODE_SIMPLE]", "[ROUTE: CODE_COMPLEX]", "[ROUTE: CONTROL]"]}
            },
            "required": ["tag"]
        }
    }
)
print("\nModel Output:")
print(res["choices"][0]["message"]["content"])
