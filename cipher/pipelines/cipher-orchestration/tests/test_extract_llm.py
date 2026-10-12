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
    assert {"entities", "events"} == _KNOWN_TASKS


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


@pytest.mark.asyncio
async def test_a_batch_failing_whole_requeues_it_and_stops(monkeypatch):
    import pyprompt

    from cipher.orchestration import extract_events
    from cipher.orchestration.run_recorder import RunStoppedError

    class _Item:
        def __init__(self, n):
            self.enrichment = type("E", (), {"id": f"enr-{n}"})()
            self.resource = {"id": f"file-{n}", "dataset_id": "d", "mime_type": "message/rfc822"}

    class _Repo:
        released, failed, completed = [], {}, []

        def __init__(self, session):
            pass

        async def count_pending(self, **k):
            return 2

        async def get_pending_batch(self, **k):
            return [_Item(1), _Item(2)]

        async def mark_processing(self, **k):
            pass

        async def release_claims(self, ids):
            _Repo.released.extend(ids)

        async def mark_failed(self, failed):
            _Repo.failed.update(failed)

        async def mark_completed_batch(self, ids):
            _Repo.completed.extend(ids)

    class _Texts:
        def __init__(self, session):
            pass

        async def get_by_file_id(self, file_id):
            return type("T", (), {"content": "Dinner Friday?", "date_content": None})()

    class _DownRunner:
        def __init__(self, settings):
            pass

        async def extract_events(self, content, reference_date=None, author=None):
            raise ConnectionError("LLM server down")

    class _Session:
        async def commit(self):
            pass

    async def _nothing(*a, **k):
        return set()

    monkeypatch.setattr(extract_events, "PostgresEnrichmentRepository", _Repo)
    monkeypatch.setattr(extract_events, "PostgresExtractedTextRepository", _Texts)
    monkeypatch.setattr(extract_events, "PostgresEventRepository", lambda session: None)
    monkeypatch.setattr(extract_events, "queue_text_event_extraction_enrichments", _nothing)
    monkeypatch.setattr(extract_events, "_load_event_dedup_keys", _nothing)
    monkeypatch.setattr(extract_events, "_reference_date", lambda extracted: None)
    monkeypatch.setattr(pyprompt, "PromptRunner", _DownRunner)

    with pytest.raises(RunStoppedError, match="back in the queue"):
        await extract_events.extract_text_events_workflow(_Session(), "d")
    assert sorted(_Repo.released) == ["enr-1", "enr-2"]
    assert _Repo.failed == {}
    assert _Repo.completed == []


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Sender", ("cathi bolton", "cathi@example.com")),
        ("we", ("cathi bolton", "cathi@example.com")),
        ("Recipient", (None, None)),
        ("You", (None, None)),
        ("Cathi", ("Cathi", None)),
    ],
)
def test_stand_in_participants_become_the_author_or_nobody(name, expected):
    from cipher.orchestration.extract_events import _llm_participant_identity
    from cipher.schemas.content.email import EmailAddress

    author = EmailAddress(name="cathi bolton", value="cathi@example.com")
    assert _llm_participant_identity(name, author) == expected


def test_author_stand_in_without_an_author_is_left_blank():
    from cipher.orchestration.extract_events import _llm_participant_identity

    assert _llm_participant_identity("Sender", None) == (None, None)
