from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ModelDevice(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"


class ClipTextRequest(BaseModel):
    text: str = Field(..., description="Text to embed")
    normalized: bool = Field(True, description="Whether to normalize the embeddings")
    model_config: ConfigDict = {
        "json_schema_extra": {
            "examples": [
                {
                    "text": "A dog on a leash which is running.",
                    "normalized": True,
                }
            ]
        }
    }
