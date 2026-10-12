from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from cipher.api.routes.search import _readable
from cipher.api.services.global_search import (
    IMAGE_HERO_MIN,
    arrange,
    plan_query,
    read_query_filters,
    visible_image_ids,
)
from cipher.schemas.graph.entity import EntitySearchResult
from cipher.schemas.interaction.global_search import Lane, LaneName, LaneStatus, QueryKind
from cipher.schemas.interaction.search_record import SearchFilters, SearchRequest


def _lanes(
    entity_score: float | None = None,
    empty: tuple[LaneName, ...] = (),
    display_name: str = "Nick Bolton",
    visible_images: int = 1,
) -> dict[LaneName, Lane]:
    lanes = {name: Lane(items=[object()]) for name in LaneName}
    lanes[LaneName.FACES] = Lane(status=LaneStatus.EMPTY)
    lanes[LaneName.IMAGES] = Lane(items=[object()], total=visible_images)
    lanes[LaneName.ENTITIES] = Lane(
        items=[]
        if entity_score is None
        else [
            EntitySearchResult(
                id="e1",
                entity_type="person",
                display_name=display_name,
                match_reason="name trigram",
                score=entity_score,
            )
        ]
    )
    for name in (*empty, *([LaneName.ENTITIES] if entity_score is None else [])):
        lanes[name] = Lane(status=LaneStatus.EMPTY)
    return lanes


def test_plan_selector_query():
    """An email address on its own is a selector query; the entity lane looks up its normalized value."""
    plan = plan_query("  nbolton04@gmail.com ")
    assert plan.kind == QueryKind.SELECTOR
    assert plan.entity_query == "nbolton04@gmail.com"


def test_plan_selector_inside_words_is_not_a_selector_query():
    """A selector inside a longer phrase leaves the query a topic."""
    assert plan_query("emails about the merger from nbolton04@gmail.com").kind == QueryKind.TOPIC


def test_plan_image_query_strips_prefix():
    """`photos of …` is an image query and only the remainder goes to CLIP."""
    plan = plan_query("Photos of the beach")
    assert plan.kind == QueryKind.IMAGE
    assert plan.image_query == "the beach"


def test_plan_question():
    """Question words or a trailing `?` mark a question."""
    assert plan_query("who did I travel to london with").is_question
    assert plan_query("london trip?").kind == QueryKind.QUESTION
    assert not plan_query("london trip").is_question


def test_arrange_strong_name_match_becomes_hero():
    """A strong entity-name match upgrades a topic to a name query with the entity card on top."""
    layout = arrange(plan_query("nick bolton"), _lanes(entity_score=0.9))
    assert layout.query_kind == QueryKind.NAME
    assert layout.hero == LaneName.ENTITIES
    assert layout.lane_order[0] == LaneName.ENTITIES


def test_arrange_weak_name_match_stays_topic():
    """A weak name match stays a topic with text first."""
    layout = arrange(plan_query("nick bolton"), _lanes(entity_score=0.4, display_name="Edmond Bolton"))
    assert layout.query_kind == QueryKind.TOPIC
    assert layout.hero is None
    assert layout.lane_order[0] == LaneName.TEXT


def test_arrange_person_name_match_by_nickname_becomes_name():
    """A low trigram score still counts when the person's name matches structurally (Nick ~ Nicholas)."""
    lanes = _lanes(entity_score=0.5, display_name="Nicholas C. Bolton")
    lanes[LaneName.FACES] = Lane(items=[object()], total=1)
    layout = arrange(plan_query("nick bolton"), lanes)
    assert layout.query_kind == QueryKind.NAME
    assert layout.lane_order[:2] == [LaneName.ENTITIES, LaneName.FACES]


def test_arrange_many_visible_images_make_an_image_query():
    """A topic whose images pass the zero-shot test leads with images, no `photos of` needed."""
    layout = arrange(plan_query("cats"), _lanes(entity_score=None, visible_images=IMAGE_HERO_MIN))
    assert layout.query_kind == QueryKind.IMAGE
    assert layout.hero == LaneName.IMAGES


def test_visible_image_ids_keeps_images_closer_to_the_query_than_generic_captions():
    """Only images whose softmax favours the query over the generic captions survive, in order."""
    query, caption = [1.0, 0.0], [0.0, 1.0]
    embeddings = {"cat": [0.9, 0.1], "doc": [0.1, 0.9], "cat2": [0.8, 0.2]}
    kept = visible_image_ids(
        query_vector=query, background=[caption], embeddings=embeddings, ids=["cat", "doc", "cat2", "missing"]
    )
    assert kept == ["cat", "cat2"]


def test_arrange_hides_empty_lanes_and_keeps_timeouts():
    """Empty lanes drop out; a timed-out lane stays so the page can link to it."""
    lanes = _lanes(entity_score=None, empty=(LaneName.EVENTS,))
    lanes[LaneName.FILES] = Lane(status=LaneStatus.TIMEOUT)
    layout = arrange(plan_query("photos of the beach"), lanes)
    assert LaneName.EVENTS not in layout.lane_order
    assert LaneName.ENTITIES not in layout.lane_order
    assert LaneName.FILES in layout.lane_order
    assert layout.hero == LaneName.IMAGES
    assert layout.image_query == "the beach"


def test_fingerprint_ignores_case_spacing_and_order_but_not_filters():
    """Same question = same record; a different filter or user is a different record."""
    base = SearchRequest(query="Nick  Bolton", dataset_ids=["b", "a"])
    assert base.fingerprint(user_id="u") == SearchRequest(query="nick bolton", dataset_ids=["a", "b"]).fingerprint(
        user_id="u"
    )
    narrowed = base.model_copy(update={"filters": SearchFilters(filetype_groups=["email"])})
    assert base.fingerprint(user_id="u") != narrowed.fingerprint(user_id="u")
    assert base.fingerprint(user_id="u") != base.fingerprint(user_id="other")


def test_filter_date_range_is_inclusive_by_day():
    """`date_to` includes its whole day."""
    start, end = SearchFilters(date_from=date(2024, 3, 1), date_to=date(2024, 3, 31)).datetime_range()
    assert start == datetime(2024, 3, 1, tzinfo=UTC)
    assert end == datetime(2024, 4, 1, tzinfo=UTC)


async def test_search_records_are_private_except_to_admins():
    """Only the owner or an admin can read a search; everyone else gets 404."""
    record = SimpleNamespace(id="s_1", user_id="owner")

    class Records:
        async def get(self, search_id):
            return record if search_id == "s_1" else None

    def access(user_id: str, is_admin: bool = False):
        return SimpleNamespace(user=SimpleNamespace(id=user_id, is_admin=is_admin))

    assert await _readable("s_1", access("owner"), Records()) is record
    assert await _readable("s_1", access("admin", is_admin=True), Records()) is record
    for search_id, who in (("s_1", "someone-else"), ("s_missing", "owner")):
        with pytest.raises(HTTPException) as error:
            await _readable(search_id, access(who), Records())
        assert error.value.status_code == 404


def test_read_query_filters_month_without_year_is_the_most_recent():
    """`in march` read in October 2026 is March 2026; in February it would be March of the year before."""
    read = read_query_filters("who emailed me about the contract in march?", today=date(2026, 10, 3))
    assert (read.date_from, read.date_to) == (date(2026, 3, 1), date(2026, 3, 31))
    assert read.filetype_groups == ("email",)
    assert read.topic == "contract"
    assert read_query_filters("trip in march", today=date(2026, 2, 1)).date_from == date(2025, 3, 1)


def test_read_query_filters_names_and_years():
    """Names come out of the topic; a bare year is the whole year; a month needs a preposition or a year."""
    read = read_query_filters("emails from megan flick in july 2025", today=date(2026, 10, 3), names=["megan flick"])
    assert (read.date_from, read.date_to, read.topic) == (date(2025, 7, 1), date(2025, 7, 31), "")
    assert read_query_filters("pdfs about the lease 2019", today=date(2026, 10, 3)).filetype_groups == ("document",)
    assert read_query_filters("may the force", today=date(2026, 10, 3)).date_from is None
    assert read_query_filters("invoice", today=date(2026, 10, 3)) == read_query_filters(
        "invoice", today=date(2026, 1, 1)
    )


def test_suggestion_searches_ticked_name_options_as_one_group():
    """Every ticked spelling/address of a typed name becomes one any-of group; unticked ones are left out."""
    from cipher.api.services.search_assist import _suggestion
    from cipher.schemas.interaction.global_search import NameChoice, NameOption
    from cipher.schemas.interaction.search_record import SearchRecord

    now = datetime.now(UTC)
    record = SearchRecord(
        id="s", user_id="u", run_count=1, query="emails from nick", date_created=now, date_last_run=now
    )
    choice = NameChoice(
        name="nick",
        options=[
            NameOption(entity_ids=["p1"], display_name="Nicholas C. Bolton", entity_type="person", is_suggested=True),
            NameOption(entity_ids=["s1", "s2"], display_name="Nick Bolton", entity_type="person", is_suggested=True),
            NameOption(entity_ids=["a1"], display_name="nick@example.com", entity_type="selector"),
        ],
    )
    suggestion = _suggestion(record, ["nick"], [choice])
    assert suggestion.request.filters.entity_groups == [["p1", "s1", "s2"]]
    assert "Nicholas C. Bolton" in suggestion.label
