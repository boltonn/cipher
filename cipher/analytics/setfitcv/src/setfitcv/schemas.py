from pydantic import BaseModel, ConfigDict, Field


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


class ImageInference(BaseModel):
    """An image embedding, plus tag head scores when classification is on."""

    embedding: list[float]
    tag_scores: dict[str, float] | None = Field(None, serialization_alias="tagScores")
    heads_version: str | None = Field(None, serialization_alias="headsVersion")


class EmbeddingsClassifyRequest(BaseModel):
    embeddings: list[list[float]] = Field(..., min_length=1, description="Normalized CLIP image embeddings")
