from llama_cpp import Llama
llm = Llama(model_path="models/iris_008.gguf", n_ctx=2048, n_gpu_layers=-1, n_threads=4, verbose=False)

web_context = """
[LIVE INTERNET SEARCH RESULTS]
- May 12, 2026 · Google is calling this new system Gemini Intelligence, and it will power a number of new Android 17 features later this year. With Gemini Intelligence, Android will be able to handle even more...
- 5 days ago · Android 17 is here with its fourth beta, confirming several new features. Plus, we already know a fair bit of what's coming, thanks to leaks!
[END LIVE INTERNET SEARCH RESULTS]
"""

system_prompt = (
    "You are Iris, a friendly and highly conversational voice assistant. "
    "Give extremely brief, concise, and natural human-sounding answers. "
)

def test_query(q):
    res = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Use the following LIVE INTERNET SEARCH RESULTS to inform your answer.\n{web_context}\n\nUser: {q}"}
        ],
        max_tokens=250, temperature=0.7
    )
    print(f"RAW A: {res['choices'][0]['message']['content']}")

test_query("Okay, can you tell me about the new Android 17?")
