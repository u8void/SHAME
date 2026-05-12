import tokenize

with open('controller.py', 'rb') as f:
    tokens = list(tokenize.tokenize(f.readline))

new_tokens = []
for tok in tokens:
    if tok.exact_type == tokenize.COMMENT:
        continue
    new_tokens.append(tok)

with open('controller.py', 'wb') as f:
    f.write(tokenize.untokenize(new_tokens))
