import sys, os
sys.path.append(os.getcwd())
from src.iris import classify_task
res = classify_task("set brightness to 40%", [])
print("Result:", res)
