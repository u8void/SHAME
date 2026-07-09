import sys
sys.path.insert(0, '/run/media/hamdy/Hamdy/IRIS/IRIS/iris-Ai')
from src.iris_control import run_stream
for event in run_stream("set brightness to 10%", [], None, {}):
    print(event)
