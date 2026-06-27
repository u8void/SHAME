import sys, os
sys.path.append(os.getcwd())
from src.iris import classify_task, load_model, ModelRole
# Override logger to see triage output before it's hidden
import logging
logging.getLogger("iris").setLevel(logging.DEBUG)

res = classify_task("set brightness to 20%", [])
print("\nFinal Result:", res)
