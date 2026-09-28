"""Face co-occurrence linker (`appears_in_photo_with` edges).

Builds an undirected person<->person edge for every pair of people detected in
the same image. A face counts towards a person if it is *assigned* to them
(verified / confirmed match / manual) **or** if it merely has a *pending*
`face_match` to them -- a single ambiguous face with pending matches to several
people contributes an edge candidate for each. So the edge appears while both
identifications are still unconfirmed, and is pruned automatically once a review
decision removes the supporting evidence.

The edge triple `(src, dst, appears_in_photo_with)` is dataset-agnostic (person
bridge nodes span datasets), so this runs **globally**, not per dataset:
`weight` is the number of distinct shared photos and `attributes["evidence"]`
lists them, each tagged `verified` (both faces assigned) or `potential`.

All the real work lives on `PostgresGraphRepository` so the backend can run the
same reconciliation inline after a face review; this module is just the CLI
entry point plus a stats helper.
"""

from typing import TYPE_CHECKING

from loguru import logger

from cipher.datastores.postgres.repositories import PostgresGraphRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def link_face_cooccurrence_workflow(session: "AsyncSession", min_verified_photos: int = 2) -> dict[str, int]:
    """Full rebuild of `appears_in_photo_with` edges from current face state.

    Args:
        session: Async DB session.
        min_verified_photos: A pair of already-identified people is only linked
            once they share this many photos; a pair with any pending-match
            photo (a lead) is linked regardless. Set to 1 to keep every
            co-occurrence.
    """
    counts = await PostgresGraphRepository(session=session).rebuild_face_cooccurrence(
        min_verified_photos=min_verified_photos
    )
    logger.success(f"Face co-occurrence linking complete: {counts}")
    return counts


async def get_face_cooccurrence_stats(session: "AsyncSession") -> dict[str, float]:
    """Edge count and summed photo weight for `appears_in_photo_with`."""
    return await PostgresGraphRepository(session=session).count_face_cooccurrence()
