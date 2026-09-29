import asyncio
from httpx import ASGITransport, AsyncClient
from cipher.api.main import app

async def main():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        ds = (await c.post("/datasets", json={"name": "test-invalidate-entity"})).json()["id"]
        try:
            ids = []
            for name in ("Weekly Digest", "Jane Roe"):
                e = (await c.post("/entities", json={"datasetId": ds, "entityType": "organization", "displayName": name})).json()
                ids.append(e["id"])
                for i in range(2):
                    r = await c.post("/mentions", json={"datasetId": ds, "entityId": e["id"], "mentionedType": "structured_field",
                        "mentionedId": f"x{i}", "surfaceText": name, "entityType": "organization", "entityAttribute": "name",
                        "normalizedValue": name.lower(), "extractor": "test"})
                    assert r.status_code == 200, r.text
            rows = (await c.get("/entities", params={"datasetId": ds, "sortBy": "mention_count", "sortOrder": "desc"})).json()["data"]
            print("list:", [(r["displayName"], r["mentionCount"]) for r in rows])
            print("discard:", (await c.delete(f"/entities/{ids[0]}", params={"discardMentions": True})).json())
            print("unlink:", (await c.delete(f"/entities/{ids[1]}")).json())
            m = (await c.get("/mentions", params={"datasetId": ds, "limit": 50})).json()
            print("remaining mentions:", [(x["surfaceText"], x["entityId"]) for x in m["data"]])
            print("review queue:", [(g["surface"], g["mentionCount"]) for g in (await c.get("/mentions/unresolved-names", params={"datasetId": ds})).json()["data"]])
        finally:
            print("cleanup dataset:", (await c.delete(f"/datasets/{ds}")).status_code)

asyncio.run(main())
