import re
s = '$$ \n <span style="border: 2px solid #4CAF50; padding: 2px 6px; border-radius: 4px; font-weight: bold; background-color: rgba(76, 175, 80, 0.1);">1 + \\binom{n}{2} + \\binom{n}{4}</span>'
print("BEFORE:")
print(s)

s = re.sub(r'</?span[\s\S]*?(?:>|&gt;|$)', '', s, flags=re.IGNORECASE)
s = re.sub(r'&lt;/?span[\s\S]*?(?:>|&gt;|$)', '', s, flags=re.IGNORECASE).strip()

print("AFTER:")
print(s)
