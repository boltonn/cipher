"""The task registry: task name -> (prompt pack, structured-output model).

Prompt packs are shipped inside the wheel (`pyproject.toml` force-include), so
`files(...)` resolves them both from source and from an installed package.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel

from pyprompt.errors import PromptPackNotFoundError
from pyprompt.schemas import LlmCombinedOutput, LlmEntityOutput, LlmEventOutput, LlmSignatureOutput
from pyprompt.templating import PromptTemplate, load_prompt

ENTITIES = "entities"
EVENTS = "events"
EXTRACT = "extract"
SIGNATURE = "signature"


@dataclass(frozen=True, slots=True)
class PromptPack:
    """One registered extraction task."""

    task: str
    relative_path: str
    output_model: type[BaseModel]

    def load(self) -> PromptTemplate:
        """Load the pack's template from package resources."""
        resource = files("pyprompt.prompts").joinpath(self.relative_path)
        return load_prompt(Path(str(resource)))


REGISTRY: dict[str, PromptPack] = {
    ENTITIES: PromptPack(task=ENTITIES, relative_path="entities/v1.md", output_model=LlmEntityOutput),
    EVENTS: PromptPack(task=EVENTS, relative_path="events/v1.md", output_model=LlmEventOutput),
    EXTRACT: PromptPack(task=EXTRACT, relative_path="extract/v1.md", output_model=LlmCombinedOutput),
    SIGNATURE: PromptPack(task=SIGNATURE, relative_path="signature/v1.md", output_model=LlmSignatureOutput),
}


def get_pack(task: str) -> PromptPack:
    """Look up a registered task, raising `PromptPackNotFoundError` if unknown."""
    try:
        return REGISTRY[task]
    except KeyError as exc:
        raise PromptPackNotFoundError(f"Unknown task '{task}'. Known: {sorted(REGISTRY)}") from exc
