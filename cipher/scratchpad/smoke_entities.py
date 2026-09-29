import asyncio, time
from httpx import ASGITransport, AsyncClient
from cipher.api.main import app

D = "42f441c8-e855-4372-99f0-a6629bfa7073"

async def main():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        for sort in ("mention_count", "display_name", "mention_count", "display_name"):
            t = time.time()
            r = await c.get("/entities", params={"datasetId": D, "sortBy": sort, "sortOrder": "desc", "limit": 5})
            print(sort, r.status_code, round(time.time() - t, 2), "s", r.json()["total"])
            for e in r.json()["data"]:
                print("  ", e["entityType"], e["displayName"][:40], e["mentionCount"], e["fileCount"], e["relationshipCount"], e["pendingMatchCount"])
        r = await c.get("/entities", params={"datasetId": D, "entityType": "person", "sortBy": "mention_count", "sortOrder": "desc", "limit": 3})
        top = r.json()["data"][0]
        print("person top", top["displayName"], top["pendingMatchCount"])
        r = await c.get("/entities/matches/groups", params={"datasetId": D, "entityId": top["id"], "status": "pending"})
        print("groups for", r.status_code, r.json()["total"], [g["surface"] for g in r.json()["data"]][:5])

asyncio.run(main())
