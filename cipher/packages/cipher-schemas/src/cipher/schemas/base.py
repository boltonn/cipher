from enum import StrEnum
from typing import Any, get_args, get_origin

from pydantic import BaseModel as PydanticBaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel, to_snake


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

    @model_validator(mode="before")
    @classmethod
    def normalize_enums(cls, data: Any) -> Any:
        """Global normalization for any field that is a StrEnum.

        Converts camelCase/PascalCase strings to the Enum's snake_case values.
        """
        if not isinstance(data, dict):
            return data

        for field_name, field_info in cls.model_fields.items():
            # Get the actual name used in the input (could be alias or snake_case)
            input_key = field_info.alias or field_name
            value = data.get(input_key) or data.get(field_name)

            if value is None or not isinstance(value, str):
                continue

            # Detect if the field is a StrEnum
            enum_type = cls._get_str_enum_type(field_info.annotation)

            if enum_type:
                # Normalize the input string
                normalized_input = to_snake(value).lower()
                for member in enum_type:
                    if member.value.lower() == normalized_input:
                        # Update the data dict with the correct enum value
                        # We update the key that was actually present
                        target_key = input_key if input_key in data else field_name
                        data[target_key] = member.value
                        break
        return data

    @staticmethod
    def _get_str_enum_type(annotation: Any) -> type[StrEnum] | None:
        """Helper to extract StrEnum from Type annotations."""
        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is None:
            if isinstance(annotation, type) and issubclass(annotation, StrEnum):
                return annotation
        else:
            # Handle Optional/Union
            for arg in args:
                if (
                    arg is not type(None)
                    and isinstance(arg, type)
                    and issubclass(arg, StrEnum)
                ):
                    return arg
        return None
