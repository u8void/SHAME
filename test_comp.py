from llama_cpp import Llama
llm = Llama(model_path="models/iris_008.gguf", n_ctx=512, n_gpu_layers=-1, n_threads=4, verbose=False)

def get_keywords(text):
    prompt = f"""Extract 2-3 search keywords from the text. If no search is needed, output None.

Text: Okay, can you tell me about the new Android 17?
Keywords: Android 17

Text: What is the capital of France?
Keywords: capital France

Text: {text}
Keywords:"""

    res = llm.create_completion(prompt=prompt, max_tokens=10, temperature=0.1, stop=["\n", "Text:"])
    return res["choices"][0]["text"].strip()

print(get_keywords("Okay, can you think about Google's new Android 17?"))
print(get_keywords("Hi, how are you?"))
