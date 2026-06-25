from src.iris import load_model, ModelRole

llm = load_model(ModelRole.GENERAL)
sys_prompt = """You are Iris AI.
[SYSTEM DIRECTIVE: The user's message is written in English. You MUST write your final response in English. If you use a <think> block for reasoning, you should reason in English inside the <think> block to ensure accuracy, and then output your final answer outside the <think> block in English.]"""

final_query = """[WEB SEARCH RESULTS]
1. The Giza pyramid complex, also called the Giza necropolis, is the site on the Giza Plateau in Greater Cairo, Egypt that includes the Great Pyramid of Giza, the Pyramid of Khafre, and the Pyramid of Menkaure, along with their associated pyramid complexes and the Great Sphinx of Giza.
[END WEB SEARCH RESULTS]

User Query:
talk about the giza pyramids

INSTRUCTIONS:
You MUST think step-by-step inside a <think> block before answering. Use the search results above to inform your answer, especially for recent events or specific facts. If the search results are incomplete, you may use your internal knowledge to supplement the answer.
Respond in the SAME LANGUAGE as the user's query."""

full_messages = [{"role": "user", "content": f"System Instructions:\n{sys_prompt}\n\n{final_query}"}]

stream = llm.create_chat_completion(
    messages=full_messages,
    stream=True,
    max_tokens=2000,
    temperature=0.4,
    repeat_penalty=1.0,
    stop=["</s>", "<|eot_id|>"]
)

for chunk in stream:
    choices = chunk.get("choices", [])
    if choices:
        delta = choices[0].get("delta", {})
        if "content" in delta:
            print(delta["content"], end="", flush=True)
print()
