import sys
from src.iris_engine import translate_text

text = """<think>
This is just a thought process. No answer.
</think>"""

res = translate_text(text, "Arabic")
print("RESULT:", repr(res))
