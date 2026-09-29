import asyncio
from sqlalchemy import text
from cipher.orchestration.cli import get_session_context
from cipher.datastores.postgres.repositories import PostgresFaceRepository
from cipher.schemas.identity.face import BaseFaceSearchParameters

async def main():
    async with get_session_context() as session:
        session.commit = session.flush  # keep everything in one rolled-back txn
        repo = PostgresFaceRepository(session=session)
        fid = (await session.execute(text("select id from face where person_id is null and embedding is not null order by random() limit 1"))).scalar()
        print("exemplar", fid)
        print("rejected", await repo.reject_faces([fid]))
        for sim in (0.7, 0.6, 0.55, 0.5, 0.4):
            ids = await repo.auto_reject_similar(exemplar_ids=[fid], min_similarity=sim)
            print(f"auto@{sim}", len(ids))
        page = await repo.search_faces(BaseFaceSearchParameters(rejected_only=True, limit=5))
        print("rejected_only total", page.total, {f.status for f in page.data}, [ (f.rejection_method, f.rejection_confidence) for f in page.data][:3])
        print("image path", len(await repo.auto_reject_similar(image_ids=["nonexistent"])))
        print("unreject", await repo.unreject_faces([fid]))
        print("left rejected", (await session.execute(text("select count(*) from face where date_rejected is not null"))).scalar())
        await session.rollback()

asyncio.run(main())
