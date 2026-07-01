import sys
from src.iris_engine import translate_text

text = """<think>
This is my thought process.
It should be preserved.
</think>
And this is the final answer!"""

print("Original:")
print(text)
print("-" * 40)

res = translate_text(text, "Arabic")
print("Translated:")
print(res)
