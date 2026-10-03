"""Train tag heads from labelled embeddings (needs the `train` extra: scikit-learn).

Per tag, a class-balanced logistic regression is fit on:
  - positives: images labelled with the tag,
  - hard negatives: images labelled "not this tag",
  - optionally unlabelled images as down-weighted negatives (most are not the tag, a few
    might be -- the low weight keeps those from dominating).
Out-of-fold predictions give the reported average precision and the per-tag threshold
(max F1); the head is then refit on everything. Training is CPU-only and takes
milliseconds per tag on CLIP-sized embeddings.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from loguru import logger

from setfitcv.heads import TagHeads


@dataclass
class TagExamples:
    """Labelled embeddings for one tag."""

    positives: np.ndarray  # [P, D]
    negatives: np.ndarray  # [N, D] hard negatives (explicitly "not this")


@dataclass
class TrainingConfig:
    """Knobs for `train_heads`."""

    min_positives: int = 8
    unlabeled_weight: float = 0.3
    regularization: float = 1.0  # sklearn `C`
    folds: int = 5


def _best_threshold(y: np.ndarray, probs: np.ndarray, weights: np.ndarray) -> tuple[float, float]:
    """(threshold, F1) maximizing weighted F1 over the out-of-fold probabilities."""
    from sklearn.metrics import precision_recall_curve

    precision, recall, thresholds = precision_recall_curve(y, probs, sample_weight=weights)
    f1 = 2 * precision * recall / np.clip(precision + recall, 1e-9, None)
    best = int(np.argmax(f1[:-1])) if len(thresholds) else 0
    return (float(thresholds[best]) if len(thresholds) else 0.5), float(f1[best])


def train_heads(
    examples: dict[str, TagExamples],
    *,
    embedding_model: str,
    unlabeled: np.ndarray | None = None,
    config: TrainingConfig | None = None,
) -> TagHeads:
    """Fit one head per tag with enough positives and stack them into a `TagHeads` bank.

    `unlabeled` ([U, D]) are random embedded images with no label for any of these tags;
    they serve as weak negatives for every tag. Tags without `min_positives` positives or
    without any negative are skipped (logged), not failed.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    config = config or TrainingConfig()
    unlabeled = unlabeled if unlabeled is not None else np.empty((0, 0), dtype=np.float32)
    tags, weights, biases, thresholds, metrics = [], [], [], [], {}

    for tag, ex in sorted(examples.items()):
        weak = unlabeled if len(unlabeled) else np.empty((0, ex.positives.shape[1]), dtype=np.float32)
        n_neg = len(ex.negatives) + len(weak)
        if len(ex.positives) < config.min_positives or n_neg == 0:
            logger.warning(
                f"Skipping {tag!r}: {len(ex.positives)} positives (need {config.min_positives}), {n_neg} negatives"
            )
            continue
        x = np.vstack([ex.positives, ex.negatives, weak]).astype(np.float32)
        y = np.concatenate([np.ones(len(ex.positives)), np.zeros(n_neg)])
        w = np.concatenate(
            [np.ones(len(ex.positives) + len(ex.negatives)), np.full(len(weak), config.unlabeled_weight)]
        )
        model = LogisticRegression(C=config.regularization, class_weight="balanced", max_iter=2000)

        folds = min(config.folds, len(ex.positives), n_neg)
        if folds >= 2:
            cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=0)
            oof = cross_val_predict(model, x, y, cv=cv, method="predict_proba", params={"sample_weight": w})[:, 1]
            ap = float(average_precision_score(y, oof, sample_weight=w))
            threshold, f1 = _best_threshold(y, oof, w)
        else:
            ap, threshold, f1 = float("nan"), 0.5, float("nan")

        model.fit(x, y, sample_weight=w)
        tags.append(tag)
        weights.append(model.coef_[0].astype(np.float32))
        biases.append(np.float32(model.intercept_[0]))
        thresholds.append(np.float32(threshold))
        metrics[tag] = {
            "positives": len(ex.positives),
            "hard_negatives": len(ex.negatives),
            "unlabeled_negatives": len(weak),
            "average_precision": ap,
            "threshold": threshold,
            "f1": f1,
        }
        logger.info(f"{tag!r}: AP={ap:.3f} F1={f1:.3f} @ {threshold:.2f} ({len(ex.positives)} pos, {n_neg} neg)")

    if not tags:
        raise ValueError("No tag had enough labelled examples to train a head")
    return TagHeads(
        tags=tags,
        weight=np.vstack(weights),
        bias=np.asarray(biases, dtype=np.float32),
        thresholds=np.asarray(thresholds, dtype=np.float32),
        embedding_model=embedding_model,
        version=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        metrics=metrics,
    )
