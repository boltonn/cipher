"""Train setfitcv tag heads on labelled image embeddings, and score images with them.

The loop: analysts label images (or accept / reject predicted tags) -> `train-image-heads`
fits one linear head per tag on the CLIP embeddings already in Postgres -> `score-image-heads`
(or `embed-images --heads-dir` at ingest) writes each head's score as a model tag score ->
the image grid's *Predicted* view surfaces them for review -> more labels -> retrain.
"""

from typing import TYPE_CHECKING

from loguru import logger

from cipher.datastores.postgres.repositories.image import PostgresImageRepository
from cipher.datastores.postgres.repositories.tag import PostgresTagRepository
from cipher.schemas.interaction.tag import TagTargetType

if TYPE_CHECKING:
    from pathlib import Path

    from setfitcv.heads import TagHeads
    from setfitcv.train import TrainingConfig
    from sqlalchemy.ext.asyncio import AsyncSession

HEADS_SOURCE_PREFIX = "setfitcv-heads:"
DEFAULT_MIN_STORED_SCORE = 0.2


async def train_image_heads_workflow(
    session: "AsyncSession",
    *,
    embedding_model: str,
    heads_dir: "Path",
    tags: list[str] | None = None,
    unlabeled_per_positive: int = 3,
    config: "TrainingConfig | None" = None,
) -> "TagHeads":
    """Fit a head per tag from labelled image embeddings and save the bank to `heads_dir`."""
    from setfitcv.train import TagExamples, train_heads

    image_repo = PostgresImageRepository(session=session)
    labelled = await image_repo.labelled_embeddings(tags=tags, embedding_model=embedding_model)
    examples = {tag: TagExamples(positives=pos, negatives=neg) for tag, (pos, neg) in labelled.items()}
    most_positives = max((len(ex.positives) for ex in examples.values()), default=0)
    unlabeled = await image_repo.sample_unlabeled_embeddings(
        tags=list(examples), embedding_model=embedding_model, limit=most_positives * unlabeled_per_positive
    )
    logger.info(f"Training {len(examples)} tag heads ({len(unlabeled)} unlabeled weak negatives)")
    heads = train_heads(examples, embedding_model=embedding_model, unlabeled=unlabeled, config=config)
    heads.save(heads_dir)
    logger.success(f"Saved {len(heads.tags)} heads ({heads.version}) to {heads_dir}")
    return heads


async def write_head_scores(
    session: "AsyncSession",
    *,
    heads: "TagHeads",
    image_ids: list[str],
    scores: list[dict[str, float]],
) -> None:
    """Store one batch's head scores as model tag scores, replacing any earlier heads version's."""
    by_tag: dict[str, dict[str, float]] = {tag: {} for tag in heads.tags}
    for image_id, row in zip(image_ids, scores, strict=True):
        for tag, score in row.items():
            by_tag[tag][image_id] = score
    await PostgresTagRepository(session).replace_scores(
        target_type=TagTargetType.CONTENT,
        target_ids=image_ids,
        scores=by_tag,
        model=heads.source_name,
        replaces=HEADS_SOURCE_PREFIX,
    )


async def score_image_heads_workflow(
    session: "AsyncSession",
    *,
    heads: "TagHeads",
    dataset_id: str | None = None,
    min_score: float = DEFAULT_MIN_STORED_SCORE,
    batch_size: int = 4096,
) -> int:
    """Score every embedded image (optionally one dataset's) from its stored embedding. Returns images scored.

    CPU matmul over stored embeddings -- no images are read and no GPU is needed; the database is the
    bottleneck. Only scores >= `min_score` are kept, so unlikely tags don't bloat `tag`.
    """
    image_repo = PostgresImageRepository(session=session)
    scored = 0
    async for image_ids, embeddings in image_repo.embedding_batches(
        embedding_model=heads.embedding_model, dataset_id=dataset_id, batch_size=batch_size
    ):
        rows = heads.as_dicts(heads.score(embeddings), min_score=min_score)
        await write_head_scores(session, heads=heads, image_ids=image_ids, scores=rows)
        scored += len(image_ids)
        logger.info(f"Scored {scored} images")
    return scored
