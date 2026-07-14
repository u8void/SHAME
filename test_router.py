import asyncio
from src.iris_triage import classify_task

async def main():
    route_gen = classify_task("integrate sin x cos x", [])
    route = None
    for x in route_gen:
        if x["type"] == "route":
            route = x["content"]
            break
    print("ROUTE IS:", route)

asyncio.run(main())
