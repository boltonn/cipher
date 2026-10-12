import enum
import re
from typing import Annotated, Any

from pydantic import (
    BaseModel as PydanticBaseModel,
    BeforeValidator,
    ConfigDict,
    GetCoreSchemaHandler,
    PlainSerializer,
    SerializationInfo,
)
from pydantic.alias_generators import to_camel, to_snake
from pydantic_core import CoreSchema, core_schema


def camelize_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Top-level keys (and `StrEnum` values) to camelCase -- for free-form dicts (e.g. a detail row) on the wire."""
    return {to_camel(k): camelize_value(v.value) if isinstance(v, StrEnum) else v for k, v in data.items()}


_SNAKE_CASE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")


def camelize_value(value: str) -> str:
    """`face_clustering` -> `faceClustering`; values that aren't snake_case pass through untouched."""
    if not _SNAKE_CASE.fullmatch(value):
        return value
    head, *rest = value.split("_")
    return head + "".join(part.capitalize() for part in rest)


def _enum_key(value: str) -> str:
    return value.replace("_", "").replace("-", "").lower()


class StrEnum(enum.StrEnum):
    """StrEnum whose values are snake_case in Python/storage and camelCase on the API wire.

    - Input: `_missing_` accepts any casing (`dateUpdated`, `DateUpdated`, `date_updated`) wherever the
      enum is validated -- model fields, `list[...]`, dict keys, FastAPI `Query()`/`Depends()` params.
    - Output: JSON dumps made *by alias* (every FastAPI response, `model_dump(mode="json", by_alias=True)`)
      emit `dateUpdated`; python-mode and non-alias dumps (DB/ES writes) keep the stored `date_updated`.
    """

    @classmethod
    def _missing_(cls, value: object) -> "StrEnum | None":
        if not isinstance(value, str):
            return None
        key = _enum_key(value)
        return next((member for member in cls if _enum_key(member.value) == key), None)

    @classmethod
    def __get_pydantic_core_schema__(cls, source: type[Any], handler: GetCoreSchemaHandler) -> CoreSchema:
        schema = handler(source)
        schema["serialization"] = core_schema.plain_serializer_function_ser_schema(cls._serialize, info_arg=True)
        return schema

    @staticmethod
    def _serialize(value: "StrEnum", info: SerializationInfo) -> "StrEnum | str":
        if not info.mode_is_json():
            return value
        return camelize_value(value.value) if info.by_alias else value.value


def _wire_value(value: str, info: SerializationInfo) -> str:
    return camelize_value(value) if info.mode_is_json() and info.by_alias else value


EnumStr = Annotated[
    str,
    BeforeValidator(lambda value: to_snake(value) if isinstance(value, str) and not value.islower() else value),
    PlainSerializer(_wire_value),
]
"""A snake_case vocabulary value from an open set (proposed verbs, feature ids, mixed-type breakdown keys).

Behaves like a `StrEnum` value on the wire: accepts camelCase in, emits camelCase by alias, stays snake_case
in storage. Prefer a real `StrEnum` whenever the set is closed.
"""


class BaseModel(PydanticBaseModel):
    """Base model for all schemas.

    Extends Pydantic's BaseModel to include a configuration that
    transforms snake case to camel case for JSON serialization.
    This makes the API responses more consistent with common JS/TS
    naming conventions.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
