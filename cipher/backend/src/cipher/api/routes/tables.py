"""Table mappings: review how a tabular layout's columns map onto the ontology, edit, verify.

Edits are re-evaluated on the mapping's stored sample: parts the user set are
locked, the rest is re-proposed around them. Verifying queues every file with the
layout for `cipher emit-tables`. See docs/tabular-mapping.md.
"""

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from cipher.api.deps.access import DatasetAccessDep
from cipher.api.deps.postgres import TableMappingDatastoreDep
from cipher.datastores.postgres.repositories.table_mapping import PostgresTableMappingRepository
from cipher.orchestration.extract_tables import requeue_mapping_files
from cipher.schemas.graph.ontology import RELATIONSHIPS
from cipher.schemas.ingestion.table_mapping import (
    FieldTypeOption,
    RelationshipVerbOption,
    TableMappingDetail,
    TableMappingRecord,
    TableMappingSummary,
    TableMappingUpdate,
    TableView,
)

router = APIRouter(prefix="/tables", tags=["tables"])


async def _accessible(datastore: PostgresTableMappingRepository, mapping_id: str, access) -> TableMappingRecord:  # noqa: ANN001
    record = await datastore.get(mapping_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Table mapping not found: {mapping_id}")
    access.require(record.dataset_id)
    return record


@router.get("/field-types", summary="The column-type vocabulary", response_model=list[FieldTypeOption])
async def list_field_types():
    """Every field type a column can be given, in vocabulary order."""
    from pytabular.fields import field_types

    return [
        FieldTypeOption(
            id=f.id,
            label=f.label,
            description=f.description,
            group=f.group,
            use=f.use.value,
            entity_type=f.entity_type,
            attribute=f.attribute,
            selector_type=f.selector_type,
            needs_ontology=f.needs_ontology,
        )
        for f in field_types().values()
    ]


@router.get(
    "/verbs", summary="Relationship verbs an edge between slots can carry", response_model=list[RelationshipVerbOption]
)
async def list_verbs():
    """Ontology verbs usable on a table row, plus proposed ones (not emitted until the ontology has them)."""
    from pytabular.detectors.llm import PROPOSED_VERBS, row_verbs

    return [
        RelationshipVerbOption(verb=verb, description=description, is_proposed=verb in PROPOSED_VERBS)
        for verb, description in row_verbs().items()
    ] + [
        RelationshipVerbOption(verb=spec.relationship_type.value, description=spec.description)
        for spec in RELATIONSHIPS.values()
        if spec.relationship_type.value not in row_verbs()
    ]


@router.get("/mappings", summary="Table mappings in your datasets", response_model=list[TableMappingSummary])
async def list_mappings(
    access: DatasetAccessDep,
    datastore: TableMappingDatastoreDep,
    dataset_ids: Annotated[list[str] | None, Query(alias="datasetIds")] = None,
):
    """One row per header layout: unverified first, with file / row counts and emit progress."""
    scope = access.scope(dataset_ids)
    if scope is None:
        from sqlalchemy import select

        from cipher.datastores.postgres.tables.dataset import DatasetTable

        scope = list((await datastore.session.execute(select(DatasetTable.id))).scalars())
    return await datastore.list_summaries(dataset_ids=scope)


@router.get("/mappings/{id}", summary="One table mapping with its files and sample", response_model=TableMappingDetail)
async def get_mapping(id: str, access: DatasetAccessDep, datastore: TableMappingDatastoreDep):
    """The mapping, the sample rows it was proposed from, and the files that use it."""
    await _accessible(datastore, id, access)
    return await datastore.detail(id)


@router.put("/mappings/{id}", summary="Edit a table mapping", response_model=TableMappingDetail)
async def update_mapping(
    id: str,
    data: Annotated[TableMappingUpdate, Body(...)],
    access: DatasetAccessDep,
    datastore: TableMappingDatastoreDep,
):
    """Save an edit and re-evaluate around it.

    Columns, slots and edges with `decisionSource = user` stay as sent; everything else
    is re-proposed on the stored sample. Any edit clears verification.
    """
    from pytabular.build import build_detectors
    from pytabular.decide import propose, sample_from_stored

    record = await _accessible(datastore, id, access)
    if data.mapping.fingerprint != record.fingerprint:
        raise HTTPException(status_code=422, detail="A mapping's header layout (fingerprint) can't change")
    region = next(
        (c.transform.region_hint for c in data.mapping.columns if c.transform and c.transform.region_hint), None
    )
    sample = sample_from_stored(record.mapping, record.sample, region=region)
    fresh = await run_in_threadpool(
        propose, sample, detectors=build_detectors(["header", "validators"]), locked=data.mapping
    )
    await datastore.save(id, mapping=fresh)
    return await datastore.detail(id)


@router.post("/mappings/{id}/verify", summary="Verify a table mapping", response_model=TableMappingDetail)
async def verify_mapping(id: str, access: DatasetAccessDep, datastore: TableMappingDatastoreDep):
    """Mark the mapping verified by you and queue its files for `cipher emit-tables` (replacing earlier output)."""
    await _accessible(datastore, id, access)
    record = await datastore.set_verified(id, user_id=access.user.id)
    await requeue_mapping_files(datastore.session, record)
    await datastore.session.commit()
    return await datastore.detail(id)


# Last: `/{sha256}` would otherwise shadow the fixed paths above.
@router.get("/{sha256}", summary="A table by content hash, with each sheet's mapping", response_model=TableView)
async def get_table(
    sha256: str,
    access: DatasetAccessDep,
    datastore: TableMappingDatastoreDep,
    dataset_id: Annotated[str | None, Query(alias="datasetId")] = None,
):
    """`mappings` is empty when the table hasn't been through `cipher map-tables` yet."""
    if dataset_id:
        access.require(dataset_id)
    file, mappings = await datastore.for_table(
        sha256, dataset_ids=None if access.dataset_ids is None else sorted(access.dataset_ids), dataset_id=dataset_id
    )
    if file is None:
        raise HTTPException(status_code=404, detail=f"Table not found: {sha256}")
    return TableView(
        sha256=sha256, file_id=file["id"], filename=file["filename"], dataset_id=file["dataset_id"], mappings=mappings
    )
