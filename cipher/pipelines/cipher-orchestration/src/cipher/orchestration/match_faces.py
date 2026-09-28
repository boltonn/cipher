"""Batch face matching (`FACE_MATCHING` analytic).

Assigns loose faces to **known people** -- the sweep counterpart to the reactive
matcher that already runs inline when an analyst adds a reference face
(`routes/persons._propose_potential_matches`). Person-level, not per-face: for
each person's representative face, KNN off the face HNSW index for still-unassigned
faces above the similarity floor and record a **pending `FaceMatch`** for analyst
review -- nothing is auto-assigned.

Cheap by construction: O(representative faces) index probes, not O(all faces).
Idempotent -- `create_matches_batch` is `ON CONFLICT DO NOTHING` on
`(face_id, person_id)`, and only `person_id IS NULL` faces are considered, so a
re-run only proposes matches for faces detected since last time.

Runs before `cluster-faces` in the pipeline: attach what belongs to known people
first, then cluster the genuine unknowns. `match-faces --reset` deletes the
pending machine-proposed matches.
"""

from typing import TYPE_CHECKING

from loguru import logger
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresFaceMatchRepository,
    PostgresFaceRepository,
    PostgresGraphRepository,
)
from cipher.schemas.identity.face import DEFAULT_FACE_MATCH_SIMILARITY
from cipher.schemas.identity.face_match import FaceMatchCreate, FaceMatchMethod

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _dedupe_matches(proposals: list[tuple[str, str, float]]) -> list[FaceMatchCreate]:
    """`(face_id, person_id, score)` proposals -> one `FaceMatchCreate` per pair, best score kept.

    A person can have several representative faces, so the same unassigned face
    can be proposed for that person more than once in a run; keep the highest
    similarity. Distinct people for one face are all kept (the review queue and
    `appears_in_photo_with` already handle an ambiguous face).
    """
    best: dict[tuple[str, str], float] = {}
    for face_id, person_id, score in proposals:
        key = (face_id, person_id)
        if score > best.get(key, -1.0):
            best[key] = score
    return [
        FaceMatchCreate(
            face_id=face_id,
            person_id=person_id,
            similarity_score=score,
            match_method=FaceMatchMethod.AUTOMATIC_SIMILARITY,
        )
        for (face_id, person_id), score in best.items()
    ]


async def match_faces_workflow(
    session: "AsyncSession",
    *,
    dataset_id: str | None = None,
    min_similarity: float = DEFAULT_FACE_MATCH_SIMILARITY,
    verified_only: bool = False,
    per_face_limit: int = 500,
    rebuild_cooccurrence: bool = True,
) -> dict[str, int]:
    """Propose pending matches from every person's representative faces. Returns counts."""
    face_repo = PostgresFaceRepository(session=session)
    match_repo = PostgresFaceMatchRepository(session=session)

    anchors = await face_repo.representative_faces(verified_only=verified_only)
    if not anchors:
        logger.warning("No representative faces to match against -- create/curate some people first.")
        return {"anchors": 0, "matches_proposed": 0, "faces_touched": 0}

    proposals: list[tuple[str, str, float]] = []
    for rep_face_id, person_id in tqdm(anchors, desc="Matching faces", unit=" anchor"):
        candidates = await face_repo.get_potential_person_matches(
            face_id=rep_face_id,
            min_similarity=min_similarity,
            limit=per_face_limit,
            dataset_id=dataset_id,
        )
        proposals.extend((face_id, person_id, score) for face_id, score in candidates)

    matches = _dedupe_matches(proposals)
    await match_repo.create_matches_batch(matches)

    touched = sorted({m.face_id for m in matches})
    if rebuild_cooccurrence and touched:
        await PostgresGraphRepository(session=session).recompute_face_cooccurrence_for_faces(touched)

    counts = {
        "anchors": len(anchors),
        "matches_proposed": len(matches),
        "faces_touched": len(touched),
    }
    logger.success(f"Face matching complete: {counts}")
    return counts


async def reset_face_matches(session: "AsyncSession", *, dataset_id: str | None = None) -> dict[str, int]:
    """Delete pending machine-proposed matches. Analyst decisions are untouched."""
    deleted = await PostgresFaceMatchRepository(session=session).delete_automatic_pending(dataset_id=dataset_id)
    await PostgresGraphRepository(session=session).rebuild_face_cooccurrence()
    logger.success(f"Reset face matches: deleted {deleted} pending automatic candidates")
    return {"deleted": deleted}
