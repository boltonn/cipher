import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelRequest, ModelResponse, ThinkingPart, ToolCallPart, ToolReturnPart, UserPromptPart

from cipher.api.agent.core import _CONTEXT_BUDGET_CHARS, _KEPT_THINKING_STEPS, _resilient, fit_context

CITATION = {
    "kind": "email",
    "fileId": "f" * 36,
    "chunkId": "c" * 36,
    "score": 0.9,
    "href": "/files/x",
    "displayName": "Re: trip",
    "snippet": "x" * 700,
    "sentTo": [f"p{i}@example.com" for i in range(9)],
}


def _long_run(steps: int) -> list:
    messages = [ModelRequest(parts=[UserPromptPart(content="question")])]
    for step in range(steps):
        call_id = f"call-{step}"
        messages.append(
            ModelResponse(
                parts=[ThinkingPart(content="t" * 3000), ToolCallPart(tool_name="search", tool_call_id=call_id)]
            )
        )
        messages.append(
            ModelRequest(
                parts=[ToolReturnPart(tool_name="search", content={"citations": [CITATION] * 10}, tool_call_id=call_id)]
            )
        )
    return messages


def _parts(messages: list, kind: type) -> list:
    return [part for message in messages for part in message.parts if isinstance(part, kind)]


def test_fit_context_stays_in_budget_and_keeps_latest_result():
    """A long tool loop is cut to the budget, oldest results first, keeping the latest steps' reasoning."""
    fitted = fit_context(_long_run(steps=8))
    returns, thinking = _parts(fitted, ToolReturnPart), _parts(fitted, ThinkingPart)
    size = sum(len(part.model_response_str()) for part in returns) + sum(len(part.content) for part in thinking)

    assert size <= _CONTEXT_BUDGET_CHARS
    assert len(thinking) == _KEPT_THINKING_STEPS
    assert isinstance(returns[-1].content, dict)
    assert isinstance(returns[0].content, str)


def test_fit_context_compacts_citations_for_the_model_only():
    """The model sees citations without card-only fields; the streamed originals are untouched."""
    original = _long_run(steps=1)
    citation = _parts(fit_context(original), ToolReturnPart)[0].content["citations"][0]

    assert not {"score", "chunkId", "href"} & citation.keys()
    assert citation["sentTo"][-1] == "+6 more"
    assert "score" in _parts(original, ToolReturnPart)[0].content["citations"][0]


async def test_a_failing_tool_reports_instead_of_ending_the_turn():
    """An unexpected error comes back to the model as a note; ModelRetry still reaches pydantic-ai."""

    async def broken(ctx) -> dict:
        raise AttributeError("bug")

    async def retry(ctx) -> dict:
        raise ModelRetry("fix the arguments")

    assert "broken failed (AttributeError)" in (await _resilient(broken)(None))["note"]
    with pytest.raises(ModelRetry):
        await _resilient(retry)(None)
