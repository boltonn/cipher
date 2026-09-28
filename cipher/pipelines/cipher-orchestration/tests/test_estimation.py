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


def test_resolve_rate_prefers_measured_once_enough_samples():
    key = (EnrichmentType.IMAGE_EMBEDDING, RunDevice.CPU)
    thin = {key: RateStat(
        enrichment_type=key[0], device=key[1], seconds_per_unit=0.2, low_per_unit=0.1, high_per_unit=0.4,
        sample_size=MIN_SAMPLES_FOR_MEASURED - 1,
    )}
    assert resolve_rate(enrichment_type=key[0], device=key[1], measured=thin).source == "seed"

    thick = {key: RateStat(
        enrichment_type=key[0], device=key[1], seconds_per_unit=0.2, low_per_unit=0.1, high_per_unit=0.4,
        sample_size=MIN_SAMPLES_FOR_MEASURED,
    )}
    resolved = resolve_rate(enrichment_type=key[0], device=key[1], measured=thick)
    assert resolved.source == "measured" and resolved.seconds_per_unit == 0.2


def test_resolve_rate_concurrency_speeds_up_llm_only():
    base = resolve_rate(enrichment_type=EnrichmentType.ENTITY_EXTRACTION, device=RunDevice.NA, measured={})
    fast = resolve_rate(
        enrichment_type=EnrichmentType.ENTITY_EXTRACTION, device=RunDevice.NA, measured={}, params={"concurrency": 4}
    )
    assert fast.seconds_per_unit < base.seconds_per_unit

    # non-LLM units ignore concurrency
    img_base = resolve_rate(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, device=RunDevice.CPU, measured={})
    img_conc = resolve_rate(
        enrichment_type=EnrichmentType.IMAGE_EMBEDDING, device=RunDevice.CPU, measured={}, params={"concurrency": 4}
    )
    assert img_base.seconds_per_unit == img_conc.seconds_per_unit


def test_estimate_enrichment_states():
    zero = estimate_enrichment(
        workload=estimate_workload(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, inventory={}),
        rate=resolve_rate(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, device=RunDevice.CPU, measured={}),
    )
    assert zero.confidence is EstimateConfidence.NONE and zero.estimate_seconds is None

    seeded = estimate_enrichment(
        workload=estimate_workload(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, inventory=INVENTORY),
        rate=resolve_rate(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, device=RunDevice.CPU, measured={}),
    )
    assert seeded.confidence is EstimateConfidence.SEEDED
    assert seeded.low_seconds <= seeded.estimate_seconds <= seeded.high_seconds


def test_prerequisites_surface_on_estimate():
    est = estimate_enrichment(
        workload=estimate_workload(enrichment_type=EnrichmentType.TEXT_EMBEDDING, inventory=INVENTORY),
        rate=resolve_rate(enrichment_type=EnrichmentType.TEXT_EMBEDDING, device=RunDevice.CPU, measured={}),
    )
    assert EnrichmentType.TEXT_EXTRACTION in est.prerequisites


def test_total_is_sequential_sum():
    a = estimate_enrichment(
        workload=estimate_workload(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, inventory=INVENTORY),
        rate=resolve_rate(enrichment_type=EnrichmentType.IMAGE_EMBEDDING, device=RunDevice.CPU, measured={}),
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
