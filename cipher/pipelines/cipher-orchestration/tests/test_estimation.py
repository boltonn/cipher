"""Pure-logic tests for enrichment time estimation (no DB)."""

from cipher.schemas.ingestion.enrichment import EnrichmentType
from cipher.schemas.ingestion.estimation import (
    MIN_SAMPLES_FOR_MEASURED,
    EstimateConfidence,
    RateStat,
    RunDevice,
    estimate_enrichment,
    estimate_workload,
    format_duration,
    resolve_rate,
    total_estimate_seconds,
)

INVENTORY = {
    "image": {"count": 1000, "size_bytes": 800_000_000},
    "document": {"count": 200, "size_bytes": 300_000_000},
    "email": {"count": 4000, "size_bytes": 120_000_000},
    "contact": {"count": 30, "size_bytes": 50_000},
    "archive": {"count": 5, "size_bytes": 10_000},
}


def test_workload_maps_groups_to_eligible_units():
    image = estimate_workload(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, inventory=INVENTORY)
    assert image.unit_count == 1000

    text = estimate_workload(enrichment_type=EnrichmentType.TEXT_EXTRACTION, inventory=INVENTORY)
    assert text.unit_count == 4200  # document + email, never archive/image

    contact = estimate_workload(enrichment_type=EnrichmentType.CONTACT_EXTRACTION, inventory=INVENTORY)
    assert contact.unit_count == 30


def test_workload_not_estimable_for_face_matching():
    w = estimate_workload(enrichment_type=EnrichmentType.FACE_MATCHING, inventory=INVENTORY)
    assert w.estimable is False and w.unit_count == 0


def test_max_pages_caps_byte_count():
    capped = estimate_workload(
        enrichment_type=EnrichmentType.TEXT_EXTRACTION, inventory=INVENTORY, params={"maxPages": 2}
    )
    assert capped.byte_count < estimate_workload(
        enrichment_type=EnrichmentType.TEXT_EXTRACTION, inventory=INVENTORY
    ).byte_count


def _measured(enrichment_type: EnrichmentType, device: RunDevice, seconds_per_unit: float = 0.2) -> dict:
    stat = RateStat(
        enrichment_type=enrichment_type,
        device=device,
        seconds_per_unit=seconds_per_unit,
        low_per_unit=seconds_per_unit / 2,
        high_per_unit=seconds_per_unit * 2,
        sample_size=MIN_SAMPLES_FOR_MEASURED,
    )
    return {(enrichment_type, device): stat}


def test_resolve_rate_is_measured_only():
    assert resolve_rate(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, device=RunDevice.CPU, measured={}) is None
    measured = _measured(EnrichmentType.IMAGE_EMBEDDING, RunDevice.CPU)
    resolved = resolve_rate(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, device=RunDevice.CPU, measured=measured)
    assert resolved.seconds_per_unit == 0.2
    # a rate measured on another device doesn't count
    assert resolve_rate(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, device=RunDevice.CUDA, measured=measured) is None


def test_resolve_rate_concurrency_speeds_up_llm_only():
    llm = _measured(EnrichmentType.EVENT_EXTRACTION, RunDevice.NA, 3.0)
    base = resolve_rate(enrichment_type=EnrichmentType.EVENT_EXTRACTION, device=RunDevice.NA, measured=llm)
    fast = resolve_rate(
        enrichment_type=EnrichmentType.EVENT_EXTRACTION, device=RunDevice.NA, measured=llm, params={"concurrency": 4}
    )
    assert fast.seconds_per_unit < base.seconds_per_unit

    img = _measured(EnrichmentType.IMAGE_EMBEDDING, RunDevice.CPU)
    img_base = resolve_rate(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, device=RunDevice.CPU, measured=img)
    img_conc = resolve_rate(
        enrichment_type=EnrichmentType.IMAGE_EMBEDDING, device=RunDevice.CPU, measured=img, params={"concurrency": 4}
    )
    assert img_base.seconds_per_unit == img_conc.seconds_per_unit


def test_estimate_enrichment_states():
    workload = estimate_workload(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, inventory=INVENTORY)
    unknown = estimate_enrichment(workload=workload, rate=None)
    assert unknown.confidence is EstimateConfidence.NONE and unknown.estimate_seconds is None

    rate = resolve_rate(
        enrichment_type=EnrichmentType.IMAGE_EMBEDDING,
        device=RunDevice.CPU,
        measured=_measured(EnrichmentType.IMAGE_EMBEDDING, RunDevice.CPU),
    )
    full = estimate_enrichment(workload=workload, rate=rate)
    assert full.confidence is EstimateConfidence.MEASURED
    assert full.low_seconds <= full.estimate_seconds <= full.high_seconds
    assert full.estimate_seconds == 1000 * 0.2

    half = estimate_enrichment(workload=workload, rate=rate, progress=0.5)
    assert half.estimate_seconds == full.estimate_seconds / 2  # only the undone share remains


def test_prerequisites_surface_on_estimate():
    est = estimate_enrichment(
        workload=estimate_workload(enrichment_type=EnrichmentType.TEXT_EMBEDDING, inventory=INVENTORY),
        rate=None,
    )
    assert EnrichmentType.TEXT_EXTRACTION in est.prerequisites


def test_total_is_sequential_sum():
    a = estimate_enrichment(
        workload=estimate_workload(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, inventory=INVENTORY),
        rate=resolve_rate(
            enrichment_type=EnrichmentType.IMAGE_EMBEDDING,
            device=RunDevice.CPU,
            measured=_measured(EnrichmentType.IMAGE_EMBEDDING, RunDevice.CPU),
        ),
    )
    b = estimate_enrichment(
        workload=estimate_workload(enrichment_type=EnrichmentType.FACE_MATCHING, inventory=INVENTORY),
        rate=None,
    )
    assert total_estimate_seconds([a, b]) == a.estimate_seconds  # b contributes nothing


def test_format_duration_scales():
    assert format_duration(None) == "n/a"
    assert format_duration(30).endswith("s")
    assert "min" in format_duration(600)
    assert format_duration(7200).endswith("h")
    assert format_duration(400_000).endswith("d")
