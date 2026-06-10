import re
from duckduckgo_search import DDGS
user_text = "Okay, can you think about Google's new Android 17?"
filler = {"okay", "can", "you", "tell", "me", "about", "the", "new", "what", "is", "who", "where", "when", "how", "please", "search", "for", "look", "up", "a", "an", "of", "to", "in", "on", "and", "that", "this", "it", "some", "more", "details", "info", "information", "hey", "iris", "do", "know", "anything", "google's", "googles"}
clean = re.sub(r'[^\w\s]', '', user_text.lower())
kw = " ".join([w for w in clean.split() if w not in filler])
print(f"Fallback KW: {kw}")
print(DDGS().text(kw, max_results=2))
