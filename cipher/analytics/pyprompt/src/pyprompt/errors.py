"""pyprompt error types."""


class PromptError(Exception):
    """Base class for pyprompt failures."""


class PromptPackNotFoundError(PromptError):
    """Requested a task/prompt pack that is not in the registry."""


class StructuredOutputError(PromptError):
    """The model did not return output matching the requested schema after all retries."""
