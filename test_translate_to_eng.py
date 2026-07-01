import sys
from src.iris_engine import translate_text

query = "قولي عن رحلة ارتيمس"
res = translate_text(query, "English")
print("RESULT:", repr(res))
