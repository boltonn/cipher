"""Rough wall-time estimates for enrichment passes over a staged dataset.

The staging milestone (files loaded + typed, so `filetype_group` / `size` are
known) fixes the file inventory. Given that inventory and a per-enrichment
throughput rate -- measured from prior `enrichment_run` rows on the same device
class, or a seeded default until enough runs accumulate -- these pure functions
produce a rough estimate per enrichment so a triager can decide what is worth
running when filing a dataset request.

Flow: `estimate_workload` (inventory -> eligible unit count) then `resolve_rate`
(measured-or-seed seconds/unit) then `estimate_enrichment` (the two combined).
"""

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas.ingestion.enrichment import EnrichmentType, enrichment_prerequisites


class WorkUnit(StrEnum):
    """The thing an enrichment's runtime scales linearly with."""

    IMAGE = "image"
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
    SEEDED = "seeded"
    NONE = "none"


# `filetype_group` values (from the filetyper) whose files carry extractable
# text. The document/email workflows filter on exactly these.
TEXT_GROUPS: tuple[str, ...] = ("document", "email")

# ~bytes of extractable content per page -- used to apply a `maxPages` cap as a
# proportional byte cut. Matches the `benchmark-storage` note that ~35k chars
# approximates a 10-page OCR'd PDF.
BYTES_PER_PAGE = 3_500

MIN_SAMPLES_FOR_MEASURED = 5

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
    EnrichmentType.ENTITY_EXTRACTION: WorkUnit.LLM_FILE,
    EnrichmentType.RELATIONSHIP_EXTRACTION: WorkUnit.LLM_FILE,
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


class SeedRate(BaseModel):
    """A conservative fallback throughput, used until real runs accumulate."""

    unit: WorkUnit
    seconds_per_unit: dict[RunDevice, float]
    fixed_overhead_seconds: float = 5.0

    def per_unit(self, device: RunDevice) -> float:
        """Seconds per unit for `device`, falling back to the CPU figure."""
        return self.seconds_per_unit.get(device) or self.seconds_per_unit[RunDevice.CPU]


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
    fixed_overhead_seconds: float
    source: Literal["measured", "seed"]
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


def _seed(unit: WorkUnit, *, cpu: float, gpu: float, na: float | None = None, overhead: float = 5.0) -> SeedRate:
    return SeedRate(
        unit=unit,
        fixed_overhead_seconds=overhead,
        seconds_per_unit={
            RunDevice.CPU: cpu,
            RunDevice.CUDA: gpu,
            RunDevice.MPS: gpu,
            RunDevice.NA: na if na is not None else cpu,
        },
    )


# Seeded from existing run logs, `benchmark-ingest` output, and conservative
# constants for served-LLM passes. Deliberately pessimistic -- a measured rate
# takes over once `MIN_SAMPLES_FOR_MEASURED` real runs exist.
DEFAULT_RATES: dict[EnrichmentType, SeedRate] = {
    EnrichmentType.TEXT_EXTRACTION: _seed(WorkUnit.TEXT_FILE, cpu=1.5, gpu=1.5),
    EnrichmentType.OCR: _seed(WorkUnit.FILE, cpu=60.0, gpu=2.0, overhead=60.0),
    EnrichmentType.TEXT_EMBEDDING: _seed(WorkUnit.TEXT_FILE, cpu=4.0, gpu=0.8),
    EnrichmentType.IMAGE_EMBEDDING: _seed(WorkUnit.IMAGE, cpu=0.6, gpu=0.08),
    EnrichmentType.FACE_DETECTION: _seed(WorkUnit.IMAGE, cpu=1.2, gpu=0.15),
    EnrichmentType.EXIF_LOCATION: _seed(WorkUnit.IMAGE, cpu=0.02, gpu=0.02, overhead=2.0),
    EnrichmentType.SELECTOR_EXTRACTION: _seed(WorkUnit.TEXT_FILE, cpu=0.3, gpu=0.3),
    EnrichmentType.ENTITY_EXTRACTION: _seed(WorkUnit.LLM_FILE, cpu=12.0, gpu=4.0, na=3.0, overhead=10.0),
    EnrichmentType.EVENT_EXTRACTION: _seed(WorkUnit.LLM_FILE, cpu=12.0, gpu=4.0, na=3.0, overhead=10.0),
    EnrichmentType.RELATIONSHIP_EXTRACTION: _seed(WorkUnit.LLM_FILE, cpu=1.0, gpu=1.0, overhead=5.0),
    EnrichmentType.CONTACT_EXTRACTION: _seed(WorkUnit.CONTACT_FILE, cpu=0.1, gpu=0.1, overhead=2.0),
}


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
    """Pick the measured rate when it has enough samples, else the seed. None when neither exists."""
    measured = measured or {}
    params = params or {}
    seed = DEFAULT_RATES.get(enrichment_type)
    unit = _UNIT.get(enrichment_type, WorkUnit.FILE)
    overhead = seed.fixed_overhead_seconds if seed else 5.0

    stat = measured.get((enrichment_type, device))
    if stat and stat.sample_size >= MIN_SAMPLES_FOR_MEASURED:
        rate = ResolvedRate(
            enrichment_type=enrichment_type,
            device=device,
            unit=unit,
            seconds_per_unit=stat.seconds_per_unit,
            low_per_unit=stat.low_per_unit,
            high_per_unit=stat.high_per_unit,
            fixed_overhead_seconds=overhead,
            source="measured",
            sample_size=stat.sample_size,
        )
    elif seed is not None:
        spu = seed.per_unit(device)
        rate = ResolvedRate(
            enrichment_type=enrichment_type,
            device=device,
            unit=unit,
            seconds_per_unit=spu,
            low_per_unit=spu * 0.6,
            high_per_unit=spu * 1.8,
            fixed_overhead_seconds=overhead,
            source="seed",
            sample_size=0,
        )
    else:
        return None

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
    """Combine an eligible workload and a resolved rate into a wall-time estimate."""
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
        return _bare("no throughput data for this analytic")

    n = workload.unit_count
    seconds = rate.fixed_overhead_seconds + n * rate.seconds_per_unit
    low = rate.fixed_overhead_seconds + n * rate.low_per_unit
    high = rate.fixed_overhead_seconds + n * rate.high_per_unit
    if rate.source == "measured":
        confidence = EstimateConfidence.MEASURED
        basis = f"median of {rate.sample_size} prior {rate.device.value} run(s)"
    else:
        confidence = EstimateConfidence.SEEDED
        basis = f"rough estimate ({rate.device.value}, no run history yet)"

    return EnrichmentEstimate(
        enrichment_type=workload.enrichment_type,
        device=rate.device,
        eligible=workload,
        prerequisites=prerequisites,
        progress=round(progress, 4),
        estimate_seconds=round(seconds, 1),
        low_seconds=round(low, 1),
        high_seconds=round(high, 1),
        confidence=confidence,
        basis=basis,
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
