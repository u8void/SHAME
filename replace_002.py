import os
import glob
from pathlib import Path

repo_dir = "/run/media/hamdy/Hamdy/IRIS/IRIS/Iris-Ai"

for root, _, files in os.walk(repo_dir):
    if ".git" in root or "__pycache__" in root:
        continue
    for file in files:
        if file.endswith((".json", ".conf", ".py", ".md")):
            path = Path(root) / file
            try:
                content = path.read_text(encoding="utf-8")
                if "iris_004.gguf" in content:
                    # Replace all occurrences of iris_004.gguf with iris_004.gguf
                    new_content = content.replace("iris_004.gguf", "iris_004.gguf")
                    path.write_text(new_content, encoding="utf-8")
                    print(f"Updated {path.relative_to(repo_dir)}")
            except Exception as e:
                pass

print("Done replacing.")
