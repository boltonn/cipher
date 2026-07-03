"""Application exceptions - used across all layers."""


class CipherError(Exception):
    """Base exception for all application errors."""

    pass


class EntityAlreadyExistsError(CipherError):
    """Raised when an entity with a unique constraint already exists."""

    def __init__(self, entity_name: str, field: str, value: str):
        self.entity_name = entity_name
        self.field = field
        self.value = value
        self.message = f"{entity_name} with {field} '{value}' already exists."
        super().__init__(self.message)


class EntityNotFoundError(CipherError):
    """Raised when a requested entity is missing."""

    def __init__(self, entity_name: str, identifier: str):
        self.entity_name = entity_name
        self.identifier = identifier
        self.message = f"{entity_name} with ID '{identifier}' not found."
        super().__init__(self.message)


class ValidationError(CipherError):
    """Raised when data validation fails."""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        self.message = f"Validation error on '{field}': {reason}"
        super().__init__(self.message)


class UnauthorizedError(CipherError):
    """Raised when user is not authorized."""

    pass


class ConfigurationError(CipherError):
    """Raised when configuration is invalid."""

    pass
