import os

main_file = "skills/coding/coding_prompt.txt"
tiny_file = "skills/coding/tiny/coding_prompt.txt"

with open(main_file, "r") as f:
    main_lines = f.readlines()

new_header = main_lines[2:9]
# Note: main_lines[2] is CRITICAL RULE:...
# main_lines[8] is the "If several different..." line

with open(tiny_file, "r") as f:
    tiny_lines = f.readlines()

# The tiny file has its line 3 as a single huge string.
tiny_line_3 = tiny_lines[2]
split_phrase = " Your code output MUST contain zero TODO comments or 'as needed' remarks."

parts = tiny_line_3.split(split_phrase)
if len(parts) == 2:
    new_tiny_line_3 = main_lines[2].strip() + "\n" + "".join(main_lines[3:8]) + main_lines[8].split(" Your code output")[0].strip() + split_phrase + parts[1]
    tiny_lines[2] = new_tiny_line_3
    with open(tiny_file, "w") as f:
        f.writelines(tiny_lines)
    print("Success")
else:
    print("Split failed")
