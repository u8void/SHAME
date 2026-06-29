import sys
import os
sys.path.append(os.path.abspath("."))
from src.iris_triage import classify_task
route, kw = classify_task("what is devil trigger", [])
print(f"Route: {route}, Keywords: {kw}")
