"""Run-plan steps must be real `cipher` commands, with pools and waits that match how they run."""

import inspect

import pytest

from cipher.orchestration.cli import app
from cipher.schemas.ingestion.run_plan import (
    STAGING_RUN,
    STEP_COMMANDS,
    PlanStep,
    RunService,
    StagingParams,
    StepPool,
    step_command,
    step_dependencies,
    step_requirements,
)

COMMANDS = {info.name: info.callback for info in app.registered_commands}


@pytest.mark.parametrize("step_type", list(STEP_COMMANDS))
def test_step_command_exists(step_type):
    assert STEP_COMMANDS[step_type] in COMMANDS


def test_staging_params_match_load_files():
    signature = inspect.signature(COMMANDS["load-files"])
    for name, field in StagingParams.model_fields.items():
        assert name in signature.parameters
        if name != "uri":
            cli_default = signature.parameters[name].default
            assert field.get_default(call_default_factory=True) == (cli_default or ([] if field.annotation == list[str] else None))


def test_staging_command():
    args = step_command(STAGING_RUN, {"uri": "s3://b/dump/", "exclude": ["*.tmp"]}, dataset_id="d1")
    assert args == ["load-files", "s3://b/dump/", "--dataset-id", "d1", "--exclude", "*.tmp"]


def test_requirements_follow_parameters():
    assert step_requirements("entity_extraction", {}).pool is StepPool.GPU
    llm = step_requirements("entity_extraction", {"extractor": "llm"})
    assert (llm.pool, llm.services) == (StepPool.CPU, [RunService.LLM])
    gated = step_requirements("event_extraction", {"llm": True})
    assert (gated.pool, gated.services) == (StepPool.GPU, [RunService.LLM])
    assert step_requirements("event_extraction", {}).pool is StepPool.CPU
    assert step_requirements("staging", {"uri": "/x"}).is_dataset_wide
    assert not step_requirements("text_embedding", {}).is_dataset_wide


def test_dependencies_within_plan():
    planned = {"staging", "archive_extraction", "text_extraction", "entity_extraction", "entity_resolution"}
    assert step_dependencies("staging", planned) == []
    assert step_dependencies("text_extraction", planned) == ["archive_extraction", "staging"]
    assert step_dependencies("entity_extraction", planned) == ["archive_extraction", "staging", "text_extraction"]
    assert "entity_extraction" in step_dependencies("entity_resolution", planned)
    assert step_dependencies("image_embedding", {"image_embedding"}) == []


def test_plan_step_validates_parameters():
    assert PlanStep(step_type="entity_extraction", parameters={"extractor": "gliner"}).parameters["extractor"] == "gliner"
    with pytest.raises(ValueError):
        PlanStep(step_type="entity_extraction", parameters={"nope": 1})
    with pytest.raises(ValueError):
        PlanStep(step_type="not_a_step")
