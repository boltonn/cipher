"""Request-form parameters must be real `cipher` options with the CLI's own defaults."""

import inspect

import pytest

from cipher.orchestration.cli import app
from cipher.orchestration.image_size import DEFAULT_MIN_IMAGE_SIDE
from cipher.schemas.ingestion.dataset_request import ANALYTIC_COMMANDS, ANALYTIC_PARAM_MODELS
from cipher.schemas.ingestion.enrichment import DEFAULT_FILETYPE_GROUPS

COMMANDS = {info.name: info.callback for info in app.registered_commands}

# CLI defaults read from .env (or None until resolved in the body) -> the value they stand for.
RESOLVED_DEFAULTS = {"min_image_side": DEFAULT_MIN_IMAGE_SIDE}


@pytest.mark.parametrize("enrichment_type", list(ANALYTIC_COMMANDS))
def test_command_exists(enrichment_type):
    assert ANALYTIC_COMMANDS[enrichment_type] in COMMANDS


@pytest.mark.parametrize("enrichment_type", list(ANALYTIC_PARAM_MODELS))
def test_params_match_cli_options(enrichment_type):
    signature = inspect.signature(COMMANDS[ANALYTIC_COMMANDS[enrichment_type]])
    for name, field in ANALYTIC_PARAM_MODELS[enrichment_type].model_fields.items():
        option = "filetype_group" if name == "filetype_groups" else name
        assert option in signature.parameters, f"{enrichment_type}: no --{option.replace('_', '-')} option"
        cli_default = RESOLVED_DEFAULTS.get(option, signature.parameters[option].default)
        if option == "filetype_group":
            cli_default = list(DEFAULT_FILETYPE_GROUPS[enrichment_type])
        cli_default = getattr(cli_default, "value", cli_default)
        assert field.get_default(call_default_factory=True) == cli_default, f"{enrichment_type}.{name}"
