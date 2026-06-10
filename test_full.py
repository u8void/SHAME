import re
from llama_cpp import Llama
from duckduckgo_search import DDGS

llm = Llama(model_path="models/iris_008.gguf", n_ctx=2048, n_gpu_layers=-1, n_threads=4, verbose=False)

user_text = "Okay, so can you tell me about Google's new Android 17?"

kw_prompt = f"Extract 2-3 search keywords from the text. If no search is needed, output None.\n\nText: Okay, can you tell me about the new Android 17?\nKeywords: Android 17\n\nText: What is the capital of France?\nKeywords: capital France\n\nText: {user_text}\nKeywords:"
kw_res = llm.create_completion(prompt=kw_prompt, max_tokens=10, temperature=0.1, stop=["\n", "Text:"])
kw = kw_res["choices"][0]["text"].strip()
print(f"Extracted KW: {kw}")

search_kw = kw.lower().replace("google's", "").replace("google", "").strip()
if not search_kw:
    search_kw = kw
print(f"Search KW: {search_kw}")

results = []
try:
    results.extend(DDGS().news(search_kw, max_results=2))
except Exception as e:
    print(f"News fail: {e}")
try:
    results.extend(DDGS().text(search_kw, max_results=2, backend="html"))
except Exception as e:
    print(f"Text fail: {e}")

web_context = ""
if results:
    web_context = "\n\n[LIVE INTERNET SEARCH RESULTS]\n"
    for r in results[:3]:
        body = r.get('body', r.get('snippet', ''))
        web_context += f"- {body}\n"
    web_context += "[END LIVE INTERNET SEARCH RESULTS]"
print(f"Web Context: {web_context}")

system_prompt = (
    "You are Iris, a friendly and highly conversational voice assistant. "
    "Give extremely brief, concise, and natural human-sounding answers. "
    "Never output your thinking process or chain of thought. Answer directly in 1-2 short sentences maximum."
)

if web_context:
    user_prompt = f"Use the following LIVE INTERNET SEARCH RESULTS to inform your answer. If they contain the answer, use it! Otherwise just chat normally.\n{web_context}\n\nUser: {user_text}"
else:
    user_prompt = user_text

res = llm.create_chat_completion(messages=[
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_prompt}
], max_tokens=250, temperature=0.7)

print(f"Final Answer: {res['choices'][0]['message']['content'].strip()}")
