"""Run plans: the steps an admin queues for a dataset, run by `cipher worker` (docs/pipeline-runner.md).

Users ask for datasets and analytics through GitHub issues (`dataset_request`); running is an
admin's job.

A plan is a set of `enrichment_run` rows sharing a `plan_id`. Each row is one step: a
`cipher` command with its parameters, the pool of host it needs (`cpu` / `gpu`), the
services it calls (the LLM), and the steps of the same plan it waits for.
"""

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from cipher.schemas._base.base import BaseModel, EnumStr, StrEnum
from cipher.schemas.ingestion.dataset_request import (
    ANALYTIC_COMMANDS,
    ANALYTIC_PARAM_MODELS,
    AnalyticRequest,
    _AnalyticParams,
)
from cipher.schemas.ingestion.enrichment import ENRICHMENT_DEPENDENCIES, RESOLUTION_RUN, EnrichmentType
from cipher.schemas.ingestion.estimation import ESTIMATE_ORDER

STAGING_RUN = "staging"
FACE_COOCCURRENCE_RUN = "face_cooccurrence"
DATASET_PROFILE_RUN = "dataset_profile"

FOLLOW_UP_STEPS: tuple[str, ...] = (RESOLUTION_RUN, FACE_COOCCURRENCE_RUN, DATASET_PROFILE_RUN)
"""Proposed after a plan finishes, never queued on their own."""

STEP_COMMANDS: dict[str, str] = {
    STAGING_RUN: "load-files",
    **{enrichment_type.value: command for enrichment_type, command in ANALYTIC_COMMANDS.items()},
    RESOLUTION_RUN: "resolve-entities",
    FACE_COOCCURRENCE_RUN: "link-face-cooccurrence",
    DATASET_PROFILE_RUN: "profile-dataset",
}
"""The `cipher` command behind every plannable step."""

STEP_ORDER: tuple[str, ...] = (
    STAGING_RUN,
    *(enrichment_type.value for enrichment_type in ESTIMATE_ORDER),
    *FOLLOW_UP_STEPS,
)


class StagingParams(_AnalyticParams):
    """`cipher load-files`: crawl a directory or `s3://bucket/prefix/` into `file` rows."""

    uri: str = Field(default="", description="Directory or s3://bucket/prefix/ to stage from (read-only)")
    include: list[str] = Field(default_factory=list, description="Globs a file's path must match (any)")
    exclude: list[str] = Field(default_factory=list, description="Globs that drop a file (any)")
    limit: int | None = Field(default=None, ge=1, description="Stop after this many files")


class StepPool(StrEnum):
    """The kind of host a step must run on."""

    CPU = "cpu"
    GPU = "gpu"


class RunService(StrEnum):
    """A shared server a step calls over HTTP; workers cap how many steps use one at once."""

    LLM = "llm"


class RunStatus(StrEnum):
    """`enrichment_run.status`. `queued` rows are plan steps not yet started."""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


HEARTBEAT_SECONDS = 30
"""How often a running step (and every `record_run`) stamps `date_heartbeat`."""
HEARTBEAT_TIMEOUT_SECONDS = 120
"""A `running` row whose heartbeat is older than this has lost its process."""

NOT_STARTED: frozenset[RunStatus] = frozenset({RunStatus.QUEUED})
LIVE: frozenset[RunStatus] = frozenset({RunStatus.RUNNING, RunStatus.CANCELLING})
FINISHED: frozenset[RunStatus] = frozenset(
    {RunStatus.CANCELLED, RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED}
)

# Steps that read or rewrite the whole dataset (or claim files their own way): one at a time
# per dataset, never split across hosts.
DATASET_WIDE_STEPS: frozenset[str] = frozenset(
    {
        STAGING_RUN,
        EnrichmentType.ARCHIVE_EXTRACTION.value,
        EnrichmentType.FACE_MATCHING.value,
        EnrichmentType.FACE_CLUSTERING.value,
        EnrichmentType.CONTACT_EXTRACTION.value,
        EnrichmentType.RELATIONSHIP_EXTRACTION.value,
        EnrichmentType.TABLE_EXTRACTION.value,
        *FOLLOW_UP_STEPS,
    }
)

_GPU_STEPS: frozenset[str] = frozenset(
    {
        EnrichmentType.TEXT_EMBEDDING.value,
        EnrichmentType.IMAGE_EMBEDDING.value,
        EnrichmentType.FACE_DETECTION.value,
        EnrichmentType.OCR.value,  # starts and stops pyvllm's `ocr` model on the GPU it is given
    }
)


class StepRequirements(BaseModel):
    """Where a step can run and what it shares."""

    pool: StepPool
    services: list[RunService] = Field(default_factory=list)
    is_dataset_wide: bool = Field(default=False, description="One at a time per dataset; never split across hosts")


def step_params(step_type: str, parameters: dict[str, Any]) -> _AnalyticParams | None:
    """Validated parameter model for a step, or `None` for a step that takes none."""
    if step_type == STAGING_RUN:
        return StagingParams.model_validate(parameters)
    if step_type in FOLLOW_UP_STEPS:
        if parameters:
            raise ValueError(f"{step_type} does not accept parameters")
        return None
    request = AnalyticRequest(enrichment_type=EnrichmentType(step_type), parameters=parameters)
    model = ANALYTIC_PARAM_MODELS.get(request.enrichment_type)
    return model.model_validate(request.parameters) if model else None


def step_requirements(step_type: str, parameters: dict[str, Any]) -> StepRequirements:
    """The pool, services and scope of a step, from its type and parameters.

    Args:
        step_type: An `EnrichmentType` value, `staging`, or a follow-up step.
        parameters: The step's parameters (either casing).
    """
    params = step_params(step_type, parameters)
    is_gpu = step_type in _GPU_STEPS
    uses_llm = step_type in {EnrichmentType.SIGNATURE_EXTRACTION.value, EnrichmentType.TEXT_SUMMARIZATION.value}
    match step_type:
        case EnrichmentType.ENTITY_EXTRACTION.value:
            uses_llm = params.extractor == "llm"
            is_gpu = not uses_llm
        case EnrichmentType.EVENT_EXTRACTION.value:
            uses_llm = params.llm
            is_gpu = params.llm and params.gate
        case EnrichmentType.TABLE_EXTRACTION.value:
            detectors = {name.strip() for name in params.detectors.split(",")}
            uses_llm = "llm" in detectors
            is_gpu = bool(detectors & {"gliner", "nerd"})
    return StepRequirements(
        pool=StepPool.GPU if is_gpu else StepPool.CPU,
        services=[RunService.LLM] if uses_llm else [],
        is_dataset_wide=step_type in DATASET_WIDE_STEPS,
    )


def step_command(step_type: str, parameters: dict[str, Any], *, dataset_id: str) -> list[str]:
    """The `cipher` argv for a step, with only the options that differ from their defaults."""
    args = [STEP_COMMANDS[step_type]]
    params = step_params(step_type, parameters)
    if isinstance(params, StagingParams):
        args.append(params.uri)
    args += ["--dataset-id", dataset_id]
    if params is None:
        return args
    defaults = type(params)().model_dump()
    for name, value in params.model_dump(exclude_none=True).items():
        if name == "uri" or value == defaults.get(name):
            continue
        option = name.removesuffix("s") if name == "filetype_groups" else name
        flag = "--" + option.replace("_", "-")
        if isinstance(value, bool):
            args.append(flag if value else flag.replace("--", "--no-", 1))
        elif isinstance(value, list):
            args += [token for item in value for token in (flag, str(item))]
        else:
            args += [flag, str(value)]
    return args


def step_dependencies(step_type: str, planned: set[str]) -> list[str]:
    """Steps of the same plan this one waits for: its prerequisites that are planned, staging first of all."""
    if step_type == STAGING_RUN:
        return []
    waits = {STAGING_RUN} & planned
    if step_type in FOLLOW_UP_STEPS:
        return sorted((planned - {step_type} - set(FOLLOW_UP_STEPS)) | waits)
    waits |= {dep.value for dep in ENRICHMENT_DEPENDENCIES.get(EnrichmentType(step_type), ())} & planned
    if EnrichmentType.ARCHIVE_EXTRACTION.value in planned and step_type != EnrichmentType.ARCHIVE_EXTRACTION.value:
        waits.add(EnrichmentType.ARCHIVE_EXTRACTION.value)
    return sorted(waits)


class PlanStep(BaseModel):
    """One step as the wizard sends it."""

    step_type: EnumStr = Field(description="An analytic (`text_extraction`, ...), `staging`, or a follow-up step")
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate(self) -> "PlanStep":
        if self.step_type not in STEP_COMMANDS:
            raise ValueError(f"Unknown step: {self.step_type}")
        params = step_params(self.step_type, self.parameters)
        self.parameters = params.model_dump(by_alias=True, exclude_none=True) if params else {}
        return self


class RunPlanCreate(BaseModel):
    """Steps an admin queues on a dataset."""

    dataset_id: str = Field(min_length=1)
    note: str | None = Field(default=None, max_length=5000)
    steps: list[PlanStep] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> "RunPlanCreate":
        types = [step.step_type for step in self.steps]
        if len(types) != len(set(types)):
            raise ValueError("The same step was planned more than once")
        return self


class CodeVersion(BaseModel):
    """The checkout a plan was approved under, or a step ran on."""

    branch: str | None = Field(default=None)
    sha: str | None = Field(default=None)
    lock_hash: str | None = Field(default=None, description="sha256 of uv.lock")


class StepProcess(BaseModel):
    """Where a step runs: find it with `ps`, read it with `tail -f <log>` on that host."""

    host: str
    worker_pid: int = Field(description="The `cipher worker` that claimed it")
    pid: int = Field(description="The step's own process (its process group leader)")
    log: str = Field(description="Its log file on that host")
    gpu: str | None = Field(default=None, description="GPU index it was given")


class PlanRun(BaseModel):
    """One step of a plan: one `enrichment_run` row."""

    id: str
    step_type: EnumStr
    command: str = Field(description="The `cipher` command it runs")
    status: RunStatus
    position: int
    pool: StepPool
    services: list[RunService] = Field(default_factory=list)
    depends_on: list[EnumStr] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    worker: str | None = Field(default=None, description="host:pid that ran it")
    process: StepProcess | None = Field(default=None)
    unit: str | None = Field(default=None)
    unit_count: int = Field(default=0)
    progress: dict | None = Field(default=None)
    error_message: str | None = Field(default=None)
    date_heartbeat: datetime | None = Field(default=None)
    date_started: datetime | None = Field(default=None)
    date_completed: datetime | None = Field(default=None)
    duration_seconds: float | None = Field(default=None)
    ran_on: CodeVersion | None = Field(default=None)
    is_version_mismatch: bool = Field(default=False, description="Ran on a different commit than approved")


class RunPlan(BaseModel):
    """A plan and its steps, in order."""

    plan_id: str
    dataset_id: str
    status: RunStatus = Field(description="Derived from the steps")
    note: str | None = Field(default=None)
    queued_by_name: str | None = Field(default=None)
    approved_on: CodeVersion | None = Field(default=None, description="The commit it was queued on")
    date_created: datetime
    date_approved: datetime | None = Field(default=None)
    steps: list[PlanRun] = Field(default_factory=list)


def plan_status(statuses: list[RunStatus]) -> RunStatus:
    """One status for a plan from its steps' statuses."""
    present = set(statuses)
    for status in (RunStatus.CANCELLING, RunStatus.RUNNING):
        if status in present:
            return status
    if RunStatus.QUEUED in present:
        return RunStatus.QUEUED
    for status in (RunStatus.FAILED, RunStatus.STOPPED, RunStatus.CANCELLED):
        if status in present:
            return status
    return RunStatus.COMPLETED


def plan_order(step_type: str) -> int:
    """Position of a step type in pipeline order."""
    return STEP_ORDER.index(step_type) if step_type in STEP_ORDER else len(STEP_ORDER)
