"""Face clustering sweep -- unsupervised identity discovery.

Groups still-unassigned faces by embedding similarity and mints one **unnamed**
`person` (`source = face_clustering`, `is_verified = false`) per cluster that
clears a configurable size floor, assigning every face in the cluster to it.
Small clusters and singletons are left unassigned. Nothing is named -- an
analyst renames / merges / splits later; the frontend filters these via
`?source=face_clustering` / `?unnamed=true`.

Built to scale: the similarity graph comes from one lateral kNN query off the
face HNSW index (`PostgresFaceRepository.knn_face_edges`), union-find runs in
memory over just the edges, and assignments are chunked bulk updates. A re-run
only ever sees faces still lacking a `person_id`, so it is incremental --
newly detected faces either form new clusters or merge into an existing
clustering person (`--no-merge` to always create fresh).

`cluster-faces --reset` is the undo: drops unverified `face_clustering` persons
and unlinks their faces.
"""

from typing import TYPE_CHECKING

from loguru import logger

from cipher.datastores.postgres.repositories import (
    PostgresEntityRepository,
    PostgresFaceRepository,
    PostgresGraphRepository,
    PostgresPersonRepository,
)
from cipher.schemas.graph.ontology import EntitySource
from cipher.schemas.identity.face import DEFAULT_FACE_SIMILARITY, FaceAssignmentMethod
from cipher.schemas.identity.person import PersonCreate, PersonSource

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class _UnionFind:
    """Minimal union-find over string ids."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, x: str) -> None:
        self._parent.setdefault(x, x)

    def find(self, x: str) -> str:
        self.add(x)
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb

    def groups(self) -> list[set[str]]:
        clusters: dict[str, set[str]] = {}
        for node in self._parent:
            clusters.setdefault(self.find(node), set()).add(node)
        return [members for members in clusters.values() if len(members) > 1]


def _clusters_from_edges(edges: list[tuple[str, str, float]]) -> list[set[str]]:
    """Connected components of the similarity graph (clusters of >= 2 faces)."""
    uf = _UnionFind()
    for a, b, _ in edges:
        uf.union(a, b)
    return uf.groups()


def _cluster_avg_similarity(edges: list[tuple[str, str, float]], members: set[str]) -> float:
    """Mean similarity of the edges wholly inside a cluster (falls back to the match floor)."""
    inside = [sim for a, b, sim in edges if a in members and b in members]
    return sum(inside) / len(inside) if inside else DEFAULT_FACE_SIMILARITY


async def cluster_faces_workflow(
    session: "AsyncSession",
    *,
    dataset_id: str | None = None,
    similarity: float = DEFAULT_FACE_SIMILARITY,
    k: int = 20,
    min_images: int = 3,
    min_faces: int = 2,
    max_faces: int = 200_000,
    merge_into_existing: bool = True,
    rebuild_cooccurrence: bool = True,
) -> dict[str, int]:
    """Cluster unassigned faces into unnamed persons. Returns per-outcome counts."""
    face_repo = PostgresFaceRepository(session=session)
    person_repo = PostgresPersonRepository(session=session)
    entity_repo = PostgresEntityRepository(session=session)

    edges = await face_repo.knn_face_edges(dataset_id=dataset_id, k=k, min_similarity=similarity, max_faces=max_faces)
    clusters = _clusters_from_edges(edges)
    logger.info(f"{len(edges)} similarity edges -> {len(clusters)} candidate clusters")

    created = merged = assigned = skipped_small = skipped_named = 0

    for members in clusters:
        member_ids = list(members)
        meta = await face_repo.faces_cluster_meta(member_ids)
        distinct_images = len({image_id for _, image_id, _, _ in meta})
        if len(member_ids) < min_faces or distinct_images < min_images:
            skipped_small += 1
            continue

        target_person_id: str | None = None
        fresh = False
        if merge_into_existing:
            nearest = await face_repo.nearest_assigned_person(member_ids, min_similarity=similarity)
            if nearest is not None:
                person_id, source, is_verified, _ = nearest
                if source == PersonSource.FACE_CLUSTERING and not is_verified:
                    target_person_id = person_id
                    merged += 1
                else:
                    # The cluster brushes a real / analyst-touched identity --
                    # leave it for the similarity-match pipeline or review.
                    skipped_named += 1
                    continue

        if target_person_id is None:
            person = await person_repo.add_person(PersonCreate(source=PersonSource.FACE_CLUSTERING, is_verified=False))
            # Bridge node so the person has an entity dossier and is visible to
            # graph traversal / face co-occurrence (which skips person ids with
            # no entity row).
            await entity_repo.upsert_person_entity(person, source=EntitySource.FACE_CLUSTERING)
            target_person_id = person.id
            created += 1
            fresh = True

        assigned += await face_repo.assign_faces_to_person(
            member_ids,
            target_person_id,
            method=FaceAssignmentMethod.AUTOMATIC,
            confidence=_cluster_avg_similarity(edges, members),
        )

        if fresh:
            best_id, *_ = max(meta, key=lambda m: ((m[2] or 0.0), (m[3] or 0.0)))
            await face_repo.set_primary_representative(best_id)

    if rebuild_cooccurrence and (created or merged):
        await PostgresGraphRepository(session=session).rebuild_face_cooccurrence()

    counts = {
        "edges": len(edges),
        "candidate_clusters": len(clusters),
        "persons_created": created,
        "clusters_merged": merged,
        "faces_assigned": assigned,
        "clusters_below_floor": skipped_small,
        "clusters_touching_named": skipped_named,
    }
    logger.success(f"Face clustering complete: {counts}")
    return counts


async def reset_face_clusters(session: "AsyncSession", *, include_verified: bool = False) -> dict[str, int]:
    """Undo `cluster-faces`: drop auto `face_clustering` persons, unlink their faces."""
    counts = await PostgresPersonRepository(session=session).purge_face_clustering(only_unverified=not include_verified)
    await PostgresGraphRepository(session=session).rebuild_face_cooccurrence()
    logger.success(f"Reset face clusters: {counts}")
    return counts
