from src.iris_triage import classify_task

route_gen = classify_task("cos x + sin x", [])
if hasattr(route_gen, "__iter__"):
    for x in route_gen:
        print("YIELD:", x)
