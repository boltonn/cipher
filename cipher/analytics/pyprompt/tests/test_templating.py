import pytest
from pyprompt.prompts.registry import ENTITIES, EVENTS, REGISTRY, get_pack
from pyprompt.templating import parse_prompt

_RAW = """---
name: sample
version: 3
description: a sample pack
---
<<SYSTEM>>
You are {{ role }}.
<<USER>>
Text:
{{ text }}
"""


def test_parse_frontmatter_and_sections():
    t = parse_prompt(_RAW)
    assert (t.name, t.version, t.description) == ("sample", "3", "a sample pack")
    system, user = t.render(role="an extractor", text="hello")
    assert system == "You are an extractor."
    assert user == "Text:\nhello"


def test_body_only_is_user_section():
    t = parse_prompt("just a {{ text }} body")
    assert t.system_template == ""
    _, user = t.render(text="X")
    assert user == "just a X body"


@pytest.mark.parametrize("task", [ENTITIES, EVENTS])
def test_registered_packs_load_and_render(task):
    template = get_pack(task).load()
    system, user = template.render(
        text="Alice flies to Berlin on 2026-05-01.",
        labels=["person", "location"],
        relation_labels=["located in"],
        reference_date="2026-04-01",
    )
    assert system and user
    assert "Alice flies to Berlin" in user


def test_registry_covers_expected_tasks():
    from pyprompt.prompts.registry import EXTRACT

    assert set(REGISTRY) == {ENTITIES, EVENTS, EXTRACT}
