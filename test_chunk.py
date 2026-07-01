import sys
from src.iris_engine import translate_text

text = """<think>
Thinking here.
</think>
This is the final answer."""

res = translate_text(text, "Arabic")
print("RESULT:", repr(res))
