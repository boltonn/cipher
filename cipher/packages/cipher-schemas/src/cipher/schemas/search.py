from typing import Annotated

from pydantic import Field

from cipher.schemas.base import BaseModel


class TextChunk(BaseModel):
    text: str
    embedding: Annotated[
        list[float], Field(description="Vector embedding of the chunk text")
    ]
    tags: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Optional tags for categorization or filtering",
        ),
    ]
    keywords: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Optional keywords extracted from the chunk",
        ),
    ]
