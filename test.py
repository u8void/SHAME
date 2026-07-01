import re
s = '$$ \n ```HTML\n <span style="font-weight: bold;">1</span>\n'
print("BEFORE:")
print(s)
s = re.sub(r'```[\s\S]*?(?:```|$)', '', s, flags=re.IGNORECASE)
print("AFTER:")
print(s)
