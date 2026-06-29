from src.controller import ai_agent_handle
for event in ai_agent_handle("Hey Iris"):
    print(event)
print("done hey")
for event in ai_agent_handle("How many words are in the phrase 'the quick brown fox jumps over a lazy dog.'"):
    print(event)
