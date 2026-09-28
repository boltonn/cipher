"""Load and render repo-resident prompt packs.

A pack is a ``.md`` file: a simple ``key: value`` frontmatter block between
``---`` fences, then a body split into a system and a user section by
``<<SYSTEM>>`` / ``<<USER>>`` markers. Both sections are Jinja2 templates.

    ---
    name: entities
    version: 1
    description: NER + relation extraction
    ---
    <<SYSTEM>>
    You are ...
    <<USER>>
    Text:
    {{ text }}
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, StrictUndefined

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SYSTEM_MARKER = "<<SYSTEM>>"
_USER_MARKER = "<<USER>>"

_env = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True, autoescape=False)


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """A parsed prompt pack."""

    name: str
    version: str
    description: str
    system_template: str
    user_template: str

    def render(self, **context: object) -> tuple[str, str]:
        """Render (system, user) with the given Jinja context."""
        system = _env.from_string(self.system_template).render(**context).strip()
        user = _env.from_string(self.user_template).render(**context).strip()
        return system, user


def parse_prompt(raw: str) -> PromptTemplate:
    """Parse a prompt-pack string into a `PromptTemplate`."""
    match = _FRONTMATTER_RE.match(raw)
    meta: dict[str, str] = {}
    body = raw
    if match:
        for line in match.group(1).splitlines():
            if ":" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
        body = raw[match.end() :]

    system_template, user_template = _split_sections(body)
    return PromptTemplate(
        name=meta.get("name", "unnamed"),
        version=meta.get("version", "0"),
        description=meta.get("description", ""),
        system_template=system_template,
        user_template=user_template,
    )


def load_prompt(path: Path) -> PromptTemplate:
    """Read and parse a prompt pack from disk."""
    return parse_prompt(path.read_text(encoding="utf-8"))


def _split_sections(body: str) -> tuple[str, str]:
    """Split a pack body into (system, user) on the section markers."""
    if _USER_MARKER not in body:
        return "", body.strip()
    head, _, user = body.partition(_USER_MARKER)
    system = head.split(_SYSTEM_MARKER, 1)[-1] if _SYSTEM_MARKER in head else ""
    return system.strip(), user.strip()


def render_custom(prompt: str, text: str | None) -> str:
    """Substitute `{text}` in a fully custom `/run` prompt (plain str.format, no Jinja)."""
    if text is None or "{text}" not in prompt:
        return prompt
    return prompt.replace("{text}", text)
