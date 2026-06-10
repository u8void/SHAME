from llama_cpp import Llama
import duckduckgo_search

llm = Llama(model_path="models/iris_008.gguf", n_ctx=2048, n_gpu_layers=-1, n_threads=4, verbose=False)

user_text = "Okay, can you think about Google's new Android 17?"
kw_prompt = f"Extract 2-3 search keywords from the text. If no search is needed, output None.\n\nText: Okay, can you tell me about the new Android 17?\nKeywords: Android 17\n\nText: What is the capital of France?\nKeywords: capital France\n\nText: {user_text}\nKeywords:"
kw_res = llm.create_completion(prompt=kw_prompt, max_tokens=10, temperature=0.1, stop=["\n", "Text:"])
kw = kw_res["choices"][0]["text"].strip()
print(f"Extracted KW: {kw}")

results = duckduckgo_search.DDGS().text(kw, max_results=2)
print(results)
