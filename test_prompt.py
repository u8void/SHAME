from llama_cpp import Llama
llm = Llama(model_path="models/iris_008.gguf", n_ctx=512, n_gpu_layers=-1, n_threads=4, verbose=False)

def test_query(q):
    res = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": "You decide if a query requires an internet search. Answer ONLY with YES or NO."},
            {"role": "user", "content": q}
        ],
        max_tokens=10, temperature=0.1
    )
    print(f"Q: {q}")
    print(f"A: {res['choices'][0]['message']['content'].strip()}\n")

test_query("Can you tell me more about the new Google's Android 17?")
test_query("Hi how are you?")
test_query("What is the capital of France?")
test_query("Tell me a funny joke.")
