import asyncio
from src.iris_triage import classify_task
from src.iris_engine import ModelRole

async def main():
    route_gen = classify_task("cos x + sin x")
    # It's an async generator? Or sync?
    print(route_gen)
    if hasattr(route_gen, "__iter__"):
        for x in route_gen:
            print("YIELD:", x)

asyncio.run(main())
