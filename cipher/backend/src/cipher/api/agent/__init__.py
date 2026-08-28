"""The CIPHER chat agent: dependencies, tools, model providers, and assembly.

Kept separate from `api/routes/chat.py` (which is only transport) so the agent's
retrieval logic is testable on its own and the toolset can grow without the
route file growing with it.
"""

from cipher.api.agent.core import build_agent
from cipher.api.agent.deps import ChatDeps
from cipher.api.agent.provider import AVAILABLE_MODELS, build_model, can_build, resolve_llm_settings

__all__ = [
    "build_agent",
    "ChatDeps",
    "AVAILABLE_MODELS",
    "build_model",
    "can_build",
    "resolve_llm_settings",
]
