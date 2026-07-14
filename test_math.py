import asyncio
from src.iris_math import run_stream

async def main():
    msgs = [{"role": "user", "content": "integrate sin x cos x"}]
    # It requires a retriever and settings
    gen = run_stream("integrate sin x cos x", msgs, None, {"user_lang": "English"})
    for x in gen:
        if x["type"] in ("token", "raw_response"):
            print(x["content"], end="")
        else:
            print(f"\n[{x['type']}]: {x.get('content', '')}\n")

asyncio.run(main())
