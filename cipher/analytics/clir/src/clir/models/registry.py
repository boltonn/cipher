from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal


class SupportedModel(StrEnum):
    JINA_EMBEDDINGS_V5 = "jina-embeddings-v5"
    MULTILINGUAL_E5 = "multilingual-e5"


@dataclass
class ModelConfig:
    pooling: Literal["mean", "last"]
    query_template: str
    passage_template: str
    use_task_id: bool  # Whether it uses LoRA/Adapter IDs


MODEL_REGISTRY = {
    SupportedModel.JINA_EMBEDDINGS_V5: ModelConfig(
        pooling="last",
        query_template="Query: ",
        passage_template="Document: ",
        use_task_id=True,
    ),
    SupportedModel.MULTILINGUAL_E5: ModelConfig(
        pooling="mean",
        query_template="query: ",
        passage_template="passage: ",
        use_task_id=False,
    ),
}


def get_model_config_from_name(model_dir: Path) -> ModelConfig:
    """Heuristic to determine model config based on the directory name."""
    name = model_dir.name.lower()
    for key, config in MODEL_REGISTRY.items():
        if key.value in name:
            return config
    raise ValueError(
        f"Model config not found for directory: {model_dir}"
        f" (tried keys: {sorted(key.value for key in MODEL_REGISTRY)})"
    )
