import re

text = "الهرم هو بناء ضخم يُستخدم في مصر ك للفراعنة. أبرز هذه الأهرامات تقع في منطقة الجيزة بالقاهرة، وتشمل هرم خوفو (أكبر الاهرامات)، وهرم خافر، وهرم م . بنيت هذه الأهرامات خلال عصر الدولة القديمة، وتُعتبر من أبرز المعالم الهندسية والـs7آية في العالم. بني الهراMك"

def clean(text):
    # Strip any Latin letters or numbers that are embedded directly inside an Arabic word (no spaces)
    text = re.sub(r'(?<=[\u0600-\u06FF])[A-Za-z0-9]+(?=[\u0600-\u06FF])', '', text)
    # Strip single Latin letters anywhere
    text = re.sub(r'(?<![A-Za-z])[A-Za-z](?![A-Za-z])', '', text)
    return text

print("ORIGINAL:", text)
print("CLEANED: ", clean(text))
