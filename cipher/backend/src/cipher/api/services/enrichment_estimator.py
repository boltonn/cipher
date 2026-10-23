"""Assemble per-enrichment time estimates for a dataset.

Wires three data sources into the pure `cipher.schemas.ingestion.estimation`
functions: the staged file inventory, measured throughput from `enrichment_run`,
and how far each enrichment has already progressed. Shared by the estimates
endpoint and the dataset-request issue body so both quote the same numbers.
"""

from datetime import UTC, datetime

from cipher.datastores.postgres.repositories.dataset import PostgresDatasetRepository
from cipher.datastores.postgres.repositories.enrichment import PostgresEnrichmentRepository
from cipher.datastores.postgres.repositories.enrichment_run import PostgresEnrichmentRunRepository
from cipher.datastores.postgres.repositories.file import PostgresFileRepository
from cipher.schemas.ingestion.enrichment import EnrichmentType
from cipher.schemas.ingestion.estimation import (
    ESTIMATE_ORDER,
    DatasetEnrichmentEstimates,
    EnrichmentEstimate,
    RunDevice,
    estimate_enrichment,
    estimate_workload,
    resolve_rate,
    run_device,
)


async def build_dataset_estimates(
    *,
    dataset_id: str,
    dataset_repo: PostgresDatasetRepository,
    file_repo: PostgresFileRepository,
    enrichment_repo: PostgresEnrichmentRepository,
    run_repo: PostgresEnrichmentRunRepository,
    only: list[EnrichmentType] | None = None,
    params_by_type: dict[EnrichmentType, dict] | None = None,
    accelerator: RunDevice = RunDevice.CUDA,
) -> DatasetEnrichmentEstimates:
    """One `EnrichmentEstimate` per enrichment (or just `only`), in pipeline order, each on its own device."""
    params_by_type = params_by_type or {}
    staging = await dataset_repo.get_staging_summary(dataset_id)
    inventory = await file_repo.get_dataset_inventory(dataset_id)
    rates = await run_repo.get_rates()
    stats = await enrichment_repo.get_enrichment_stats(dataset_id=dataset_id)

    wanted = list(only) if only else list(ESTIMATE_ORDER)
    items: list[EnrichmentEstimate] = []
    for enrichment_type in ESTIMATE_ORDER:
        if enrichment_type not in wanted:
            continue
        params = params_by_type.get(enrichment_type, {})
        workload = estimate_workload(enrichment_type=enrichment_type, inventory=inventory, params=params)
        rate = resolve_rate(
            enrichment_type=enrichment_type,
            device=run_device(enrichment_type, accelerator=accelerator, params=params),
            measured=rates,
            params=params,
        )
        counts = stats.get(enrichment_type, {}) or {}
        total = sum(counts.values())
        progress = ((counts.get("completed", 0) + counts.get("skipped", 0)) / total) if total else 0.0
        items.append(estimate_enrichment(workload=workload, rate=rate, progress=progress))

    return DatasetEnrichmentEstimates(
        dataset_id=dataset_id,
        is_staged=staging.is_staged,
        accelerator=accelerator,
        date_generated=datetime.now(UTC),
        items=items,
    )
