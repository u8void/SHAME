from src.iris import _stream_tokens, ModelRole, TaskType

web_context = "The Giza pyramid complex, also called the Giza necropolis, is the site on the Giza Plateau in Greater Cairo, Egypt that includes the Great Pyramid of Giza, the Pyramid of Khafre, and the Pyramid of Menkaure, along with their associated pyramid complexes and the Great Sphinx of Giza."
user_query = "talk about the giza pyramids"

final_query = (
    f"[WEB SEARCH RESULTS]\n{web_context}\n[END WEB SEARCH RESULTS]\n\n"
    f"User Query: {user_query}\n\n"
    f"INSTRUCTIONS: You MUST think step-by-step inside a <think> block before answering. "
    f"Use the search results above to inform your answer, especially for recent events or specific facts. "
    f"If the search results are incomplete, you may use your internal knowledge to supplement the answer. "
    f"Respond in the SAME LANGUAGE as the user's query."
)

messages = [{"role": "user", "content": final_query}]
for ev in _stream_tokens(ModelRole.GENERAL, messages, max_tokens=200):
    if ev["type"] == "token" or ev["type"] == "thinking":
        print(ev["content"], end="", flush=True)
print()
