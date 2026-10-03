"""Rough wall-time estimates for enrichment passes over a staged dataset.

The staging milestone (files loaded + typed, so `filetype_group` / `size` are
known) fixes the file inventory. Given that inventory and a per-enrichment
throughput rate measured from prior `enrichment_run` rows on the same device
class, these pure functions estimate the remaining time per enrichment so a
triager can decide what is worth running. No run history means no estimate --
nothing is guessed.

Flow: `estimate_workload` (inventory -> eligible unit count) then `resolve_rate`
(measured seconds/unit) then `estimate_enrichment` (the two combined).
"""

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas.ingestion.enrichment import EnrichmentType, enrichment_prerequisites


class WorkUnit(StrEnum):
    """The thing an enrichment's runtime scales linearly with."""

    IMAGE = "image"
    FACE = "face"
    TEXT_FILE = "text_file"
    LLM_FILE = "llm_file"
    CONTACT_FILE = "contact_file"
    MESSAGE = "message"
    FILE = "file"


class RunDevice(StrEnum):
    """Inference device class a run executed on -- rates are keyed by it."""

    CPU = "cpu"
    CUDA = "cuda"
    MPS = "mps"
    NA = "na"


# Analytics whose CLI takes `--device`; every other analytic has a fixed device.
DEVICE_SELECTABLE: frozenset[EnrichmentType] = frozenset(
    {EnrichmentType.TEXT_EMBEDDING, EnrichmentType.IMAGE_EMBEDDING, EnrichmentType.FACE_DETECTION}
)
GPU_ONLY: frozenset[EnrichmentType] = frozenset({EnrichmentType.OCR})


def run_device(enrichment_type: EnrichmentType, accelerator: RunDevice = RunDevice.CUDA) -> RunDevice:
    """The device class an analytic actually runs on, matching what `record_run` stores.

    Args:
        enrichment_type: The analytic.
        accelerator: Device used by analytics that accept `--device`.

    Returns:
        `accelerator` for device-selectable analytics, CUDA for GPU-only ones, else NA.
    """
    if enrichment_type in DEVICE_SELECTABLE:
        return accelerator
    if enrichment_type in GPU_ONLY:
        return RunDevice.CUDA
    return RunDevice.NA


class EstimateConfidence(StrEnum):
    MEASURED = "measured"
    NONE = "none"


# `filetype_group` values (from the filetyper) whose files carry extractable
# text. The document/email workflows filter on exactly these.
TEXT_GROUPS: tuple[str, ...] = ("document", "email")

# ~bytes of extractable content per page -- used to apply a `maxPages` cap as a
# proportional byte cut. Matches the `benchmark-storage` note that ~35k chars
# approximates a 10-page OCR'd PDF.
BYTES_PER_PAGE = 3_500

MIN_SAMPLES_FOR_MEASURED = 1

# Surfaced in the request wizard, roughly in pipeline order.
ESTIMATE_ORDER: tuple[EnrichmentType, ...] = (
    EnrichmentType.TEXT_EXTRACTION,
    EnrichmentType.OCR,
    EnrichmentType.TEXT_EMBEDDING,
    EnrichmentType.IMAGE_EMBEDDING,
    EnrichmentType.EXIF_LOCATION,
    EnrichmentType.FACE_DETECTION,
    EnrichmentType.FACE_MATCHING,
    EnrichmentType.FACE_CLUSTERING,
    EnrichmentType.CONTACT_EXTRACTION,
    EnrichmentType.SELECTOR_EXTRACTION,
    EnrichmentType.ENTITY_EXTRACTION,
    EnrichmentType.RELATIONSHIP_EXTRACTION,
    EnrichmentType.EVENT_EXTRACTION,
)

_ELIGIBLE_GROUPS: dict[EnrichmentType, tuple[str, ...]] = {
    EnrichmentType.IMAGE_EMBEDDING: ("image",),
    EnrichmentType.EXIF_LOCATION: ("image",),
    EnrichmentType.FACE_DETECTION: ("image",),
    EnrichmentType.TEXT_EXTRACTION: TEXT_GROUPS,
    # Upper bound: only image-based PDF pages + (optionally CLIP-filtered) images are OCR'd.
    EnrichmentType.OCR: ("document", "image"),
    EnrichmentType.TEXT_EMBEDDING: TEXT_GROUPS,
    EnrichmentType.SELECTOR_EXTRACTION: TEXT_GROUPS,
    EnrichmentType.ENTITY_EXTRACTION: TEXT_GROUPS,
    EnrichmentType.RELATIONSHIP_EXTRACTION: TEXT_GROUPS,
    EnrichmentType.EVENT_EXTRACTION: TEXT_GROUPS,
    EnrichmentType.CONTACT_EXTRACTION: ("contact",),
}

_UNIT: dict[EnrichmentType, WorkUnit] = {
    EnrichmentType.IMAGE_EMBEDDING: WorkUnit.IMAGE,
    EnrichmentType.EXIF_LOCATION: WorkUnit.IMAGE,
    EnrichmentType.FACE_DETECTION: WorkUnit.IMAGE,
    EnrichmentType.FACE_MATCHING: WorkUnit.IMAGE,
    EnrichmentType.FACE_CLUSTERING: WorkUnit.IMAGE,
    EnrichmentType.TEXT_EXTRACTION: WorkUnit.TEXT_FILE,
    EnrichmentType.OCR: WorkUnit.FILE,
    EnrichmentType.TEXT_EMBEDDING: WorkUnit.TEXT_FILE,
    EnrichmentType.SELECTOR_EXTRACTION: WorkUnit.TEXT_FILE,
    EnrichmentType.ENTITY_EXTRACTION: WorkUnit.TEXT_FILE,
    EnrichmentType.RELATIONSHIP_EXTRACTION: WorkUnit.TEXT_FILE,
    EnrichmentType.EVENT_EXTRACTION: WorkUnit.LLM_FILE,
    EnrichmentType.CONTACT_EXTRACTION: WorkUnit.CONTACT_FILE,
    EnrichmentType.MESSAGE_TRANSLATION: WorkUnit.MESSAGE,
}


class EnrichmentWorkload(BaseModel):
    """The eligible slice of a dataset an enrichment would process."""

    enrichment_type: EnrichmentType
    unit: WorkUnit
    unit_count: int = 0
    byte_count: int = 0
    estimable: bool = True
    note: str | None = None


class RateStat(BaseModel):
    """Measured seconds-per-unit percentiles for one (enrichment, device)."""

    enrichment_type: EnrichmentType
    device: RunDevice
    seconds_per_unit: float
    low_per_unit: float
    high_per_unit: float
    sample_size: int


class ResolvedRate(BaseModel):
    """The throughput an estimate is actually computed from."""

    enrichment_type: EnrichmentType
    device: RunDevice
    unit: WorkUnit
    seconds_per_unit: float
    low_per_unit: float
    high_per_unit: float
    sample_size: int


class EnrichmentEstimate(BaseModel):
    """A rough wall-time estimate for one enrichment over one dataset."""

    enrichment_type: EnrichmentType
    device: RunDevice = RunDevice.NA
    eligible: EnrichmentWorkload
    estimate_seconds: float | None = None
    low_seconds: float | None = None
    high_seconds: float | None = None
    confidence: EstimateConfidence = EstimateConfidence.NONE
    basis: str
    prerequisites: list[EnrichmentType] = Field(default_factory=list)
    progress: float = 0.0


class DatasetEnrichmentEstimates(BaseModel):
    """Per-enrichment estimates for one dataset, each on the device it runs on."""

    dataset_id: str
    is_staged: bool
    accelerator: RunDevice
    date_generated: datetime
    items: list[EnrichmentEstimate]


def estimate_workload(
    *,
    enrichment_type: EnrichmentType,
    inventory: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> EnrichmentWorkload:
    """Map a `get_dataset_inventory` dict to the eligible unit count for one enrichment."""
    unit = _UNIT.get(enrichment_type, WorkUnit.FILE)
    groups = _ELIGIBLE_GROUPS.get(enrichment_type)
    if groups is None:
        if enrichment_type in (EnrichmentType.FACE_MATCHING, EnrichmentType.FACE_CLUSTERING):
            note = "runs after face detection; scales with detected faces"
        else:
            note = "scales with message count, not the file inventory"
        return EnrichmentWorkload(enrichment_type=enrichment_type, unit=unit, estimable=False, note=note)

    params = params or {}
    unit_count = 0
    byte_count = 0
    for group in groups:
        info = inventory.get(group)
        if not info:
            continue
        unit_count += int(info.get("count", 0))
        byte_count += int(info.get("size_bytes", 0))

    max_pages = params.get("maxPages") or params.get("max_pages")
    if max_pages and unit_count:
        byte_count = min(byte_count, unit_count * int(max_pages) * BYTES_PER_PAGE)

    return EnrichmentWorkload(enrichment_type=enrichment_type, unit=unit, unit_count=unit_count, byte_count=byte_count)


def resolve_rate(
    *,
    enrichment_type: EnrichmentType,
    device: RunDevice,
    measured: dict[tuple[EnrichmentType, RunDevice], RateStat] | None = None,
    params: dict[str, Any] | None = None,
) -> ResolvedRate | None:
    """The measured rate for this analytic on this device; None until it has run here."""
    params = params or {}
    stat = (measured or {}).get((enrichment_type, device))
    if stat is None or stat.sample_size < MIN_SAMPLES_FOR_MEASURED:
        return None
    rate = ResolvedRate(
        enrichment_type=enrichment_type,
        device=device,
        unit=_UNIT.get(enrichment_type, WorkUnit.FILE),
        seconds_per_unit=stat.seconds_per_unit,
        low_per_unit=stat.low_per_unit,
        high_per_unit=stat.high_per_unit,
        sample_size=stat.sample_size,
    )

    concurrency = int(params.get("concurrency", 1) or 1)
    if rate.unit == WorkUnit.LLM_FILE and concurrency > 1:
        factor = 1.0 / min(concurrency, 8)
        rate.seconds_per_unit *= factor
        rate.low_per_unit *= factor
        rate.high_per_unit *= factor

    return rate


def estimate_enrichment(
    *,
    workload: EnrichmentWorkload,
    rate: ResolvedRate | None,
    progress: float = 0.0,
) -> EnrichmentEstimate:
    """Combine an eligible workload and a measured rate into the remaining wall time (the undone share)."""
    prerequisites = enrichment_prerequisites(workload.enrichment_type)

    def _bare(basis: str) -> EnrichmentEstimate:
        return EnrichmentEstimate(
            enrichment_type=workload.enrichment_type,
            device=rate.device if rate else RunDevice.NA,
            eligible=workload,
            prerequisites=prerequisites,
            progress=round(progress, 4),
            confidence=EstimateConfidence.NONE,
            basis=basis,
        )

    if not workload.estimable:
        return _bare(workload.note or "not estimable from the file inventory")
    if workload.unit_count == 0:
        return _bare("no eligible files in this dataset")
    if rate is None:
        return _bare("no run history yet")

    remaining = workload.unit_count * (1.0 - min(max(progress, 0.0), 1.0))
    runs = "run" if rate.sample_size == 1 else "runs"

    return EnrichmentEstimate(
        enrichment_type=workload.enrichment_type,
        device=rate.device,
        eligible=workload,
        prerequisites=prerequisites,
        progress=round(progress, 4),
        estimate_seconds=round(remaining * rate.seconds_per_unit, 1),
        low_seconds=round(remaining * rate.low_per_unit, 1),
        high_seconds=round(remaining * rate.high_per_unit, 1),
        confidence=EstimateConfidence.MEASURED,
        basis=f"median of {rate.sample_size} prior {rate.device.value} {runs}",
    )


def total_estimate_seconds(estimates: Iterable[EnrichmentEstimate]) -> float:
    """Sequential-run total: analytics run one after another, so estimates add up."""
    return round(sum(e.estimate_seconds or 0.0 for e in estimates), 1)


def format_duration(seconds: float | None) -> str:
    """Compact human string: `~45s`, `~12 min`, `~2.5 h`, `~1.4 d`."""
    if seconds is None:
        return "n/a"
    if seconds < 90:
        return f"~{round(seconds)}s"
    minutes = seconds / 60
    if minutes < 90:
        return f"~{round(minutes)} min"
    hours = minutes / 60
    if hours < 36:
        return f"~{hours:.1f} h"
    return f"~{hours / 24:.1f} d"
