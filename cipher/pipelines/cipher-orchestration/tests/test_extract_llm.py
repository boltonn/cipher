"""Pure-logic tests for the combined LLM pass: task validation, the size cap, persist helpers."""

import pytest

from cipher.orchestration import extract_llm as mod
from cipher.orchestration.extract_llm import _KNOWN_TASKS, LlmPassTooLargeError, extract_llm_workflow


@pytest.mark.asyncio
async def test_rejects_unknown_task():
    with pytest.raises(ValueError, match="unknown task"):
        await extract_llm_workflow(None, "d", tasks={"summary"})


@pytest.mark.asyncio
async def test_rejects_empty_tasks():
    with pytest.raises(ValueError, match="at least one task"):
        await extract_llm_workflow(None, "d", tasks=set())


def test_known_tasks_are_entities_and_events():
    assert _KNOWN_TASKS == {"entities", "events"}


class _FakeEnrichmentRepo:
    def __init__(self, session=None, pending=0):
        self._pending = pending

    async def queue_enrichments_by_filter(self, **k):
        return 0

    async def count_pending(self, **k):
        return self._pending


@pytest.mark.asyncio
async def test_refuses_a_pass_over_the_cap(monkeypatch):
    monkeypatch.setattr(mod, "PostgresEnrichmentRepository", lambda session: _FakeEnrichmentRepo(pending=50_000))

    class _NoCommit:
        async def commit(self):
            pass

    with pytest.raises(LlmPassTooLargeError, match="cap for one LLM pass"):
        await extract_llm_workflow(_NoCommit(), "d", tasks={"entities"}, max_files=15_000)


@pytest.mark.asyncio
async def test_limit_below_cap_is_allowed_past_the_gate(monkeypatch):
    monkeypatch.setattr(mod, "PostgresEnrichmentRepository", lambda session: _FakeEnrichmentRepo(pending=50_000))

    # A tiny --limit keeps the run under the cap even with a huge backlog; the
    # gate must not fire (it fails later, on the real PromptRunner, which is fine).
    class _NoCommit:
        async def commit(self):
            pass

    with pytest.raises(Exception) as exc:  # noqa: PT011 -- want "not LlmPassTooLargeError"
        await extract_llm_workflow(_NoCommit(), "d", tasks={"entities"}, limit=10, max_files=15_000)
    assert not isinstance(exc.value, LlmPassTooLargeError)


@pytest.mark.asyncio
async def test_persist_llm_events_dedups_within_a_call():
    from pyprompt.runner import _coerce_event
    from pyprompt.schemas import LlmEvent

    from cipher.orchestration.extract_events import persist_llm_events

    class _FakeEventRepo:
        def __init__(self):
            self.added = []

        async def add_event(self, create):
            self.added.append(create)

            class _E:
                id = "e"

            return _E()

        async def add_participant(self, **k):
            pass

        async def add_place(self, **k):
            pass

    repo = _FakeEventRepo()
    same = [
        _coerce_event(LlmEvent(title="Weekly sync", event_type="meeting", date_start="2026-09-15T10:00:00")),
        _coerce_event(LlmEvent(title="weekly  SYNC", event_type="meeting", date_start="2026-09-15T18:00:00")),
    ]
    written = await persist_llm_events(same, dataset_id="d", file_id="f", model="m", seen=set(), event_repo=repo)
    assert written == 1
    assert len(repo.added) == 1
