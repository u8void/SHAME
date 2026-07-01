import re
from deep_translator import GoogleTranslator

def translate_text(text: str, target_lang: str) -> str:
    target = target_lang.lower().strip()
    if target == "english" or not target:
        return text

    # Protect code blocks
    code_blocks = []
    def protect_code(m):
        code_blocks.append(m.group(0))
        return f"\n<PROTECTED_CODE_{len(code_blocks)-1}>\n"
    
    # Protect inline code
    inline_code = []
    def protect_inline(m):
        inline_code.append(m.group(0))
        return f"<PROTECTED_INLINE_{len(inline_code)-1}>"

    # Protect math blocks
    math_blocks = []
    def protect_math(m):
        math_blocks.append(m.group(0))
        return f"\n<PROTECTED_MATH_{len(math_blocks)-1}>\n"

    temp = re.sub(r'```[\s\S]*?```', protect_code, text)
    temp = re.sub(r'\$\$[\s\S]*?\$\$', protect_math, temp)
    temp = re.sub(r'`[^`]+`', protect_inline, temp)

    # Split by newlines so we don't hit the 5000 character limit of GoogleTranslator
    # and to preserve markdown structure
    lines = temp.split('\n')
    translated_lines = []
    
    try:
        translator = GoogleTranslator(source='auto', target=target)
        for line in lines:
            if not line.strip() or line.strip().startswith("<PROTECTED_"):
                translated_lines.append(line)
            else:
                # Max chars is 5000, we should be safe per-line
                translated_lines.append(translator.translate(line))
                
        final_text = '\n'.join(translated_lines)
    except Exception as e:
        print(f"Translation failed: {e}")
        return text

    # Restore placeholders
    for i, code in enumerate(code_blocks):
        final_text = re.sub(fr'<PROTECTED_CODE_{i}>', lambda m, c=code: c, final_text)
    for i, math in enumerate(math_blocks):
        final_text = re.sub(fr'<PROTECTED_MATH_{i}>', lambda m, c=math: c, final_text)
    for i, inline in enumerate(inline_code):
        final_text = re.sub(fr'<PROTECTED_INLINE_{i}>', lambda m, c=inline: c, final_text)

    return final_text

sample = """Here is the math:
$$ 1 + 1 = 2 $$
And the code:
```python
def x():
    print("hello")
```
Also `inline code` here."""

print(translate_text(sample, 'arabic'))
