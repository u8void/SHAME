from src.iris_engine import detect_user_language, translate_text

query = "قولي عن رحلة ارتيمس"
lang = detect_user_language(query)
print("Language:", lang)

text = """<think>
The user is asking about the Artemis mission in Arabic.
I will search the web and summarize the information.
</think>
The Artemis program is a robotic and human moon exploration program led by NASA.
It aims to return humans to the Moon by 2025.
"""

translated = translate_text(text, lang)
print("Translated:")
print(repr(translated))
