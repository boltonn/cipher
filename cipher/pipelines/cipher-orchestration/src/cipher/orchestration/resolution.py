"""The entity-resolution stage, one call: match -> decide -> derive (`docs/entity-resolution.md` §0).

1. **Match + decide** (`resolve_entities_workflow`), per unit -- one name key: same names settle
   first (fold same-type auto-created duplicates, attach names to their auto-created entity), then
   each unit's names are scored against entities, then auto-created entities new since the last
   run are scored against other entities.
2. **Places** -- location mentions against the offline gazetteer.
3. **Links and suggestions** -- header identifier links, relationship and email-domain
   suggestions, event participant links, then closing suggestions whose names are resolved.

Recorded as one `enrichment_run` (`entity_resolution`) whose `progress` holds each step's
done / total while it runs -- the dataset page shows it as the Resolve stage.
"""

import asyncio
import os
from time import monotonic

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRunRepository,
    PostgresGraphRepository,
    PostgresMentionRelationshipRepository,
)
from cipher.orchestration.domain_affiliations import propose_domain_affiliations
from cipher.orchestration.family_links import propose_family_from_patronymics
from cipher.orchestration.resolve_entities import reconcile_resolved_name_groups, resolve_entities_workflow
from cipher.orchestration.resolve_event_links import resolve_event_links_workflow
from cipher.orchestration.resolve_locations import resolve_locations_workflow
from cipher.orchestration.run_recorder import RUN_ID_ENV, keep_alive
from cipher.orchestration.session import get_async_engine_from_settings
from cipher.places import default_gazetteer_path
from cipher.schemas.graph.entity_resolution import EntityResolutionConfig
from cipher.schemas.ingestion.enrichment import RESOLUTION_RUN

RESOLUTION_STEPS = (
    ("same_names", "Same names"),
    ("names", "Match names"),
    ("short_names", "Short names in context"),
    ("entities", "Match new entities"),
    ("places", "Places"),
    ("links", "Links and suggestions"),
)
_WRITE_EVERY_SECONDS = 2.0


class StepProgress:
    """The run's per-step progress on `enrichment_run.progress`, written at most every 2 seconds."""

    def __init__(self, engine: AsyncEngine, run_id: str):
        self.engine = engine
        self.run_id = run_id
        self.steps = {
            name: {"name": name, "label": label, "done": 0, "total": 0, "status": "pending"}
            for name, label in RESOLUTION_STEPS
        }
        self._written = 0.0
        self._lock = asyncio.Lock()

    async def __call__(self, step: str, done: int, total: int) -> None:
        """Advance `step`; it completes when `done` reaches `total`."""
        finished = done >= total
        self.steps[step].update(done=done, total=total, status="completed" if finished else "running")
        await self._write(force=finished)

    async def _write(self, *, force: bool = False) -> None:
        if not force and monotonic() - self._written < _WRITE_EVERY_SECONDS:
            return
        async with self._lock, AsyncSession(self.engine) as session:
            await PostgresEnrichmentRunRepository(session=session).set_progress(
                self.run_id, {"steps": list(self.steps.values())}
            )
            self._written = monotonic()


async def _links(
    session: AsyncSession, dataset_id: str, *, link_selectors: bool, progress: StepProgress
) -> dict[str, int]:
    """Everything derived from settled identities, in dependency order."""
    counts: dict[str, int] = {}
    steps = [
        ("has_selector_edges", lambda: PostgresGraphRepository(session=session).link_header_selectors(dataset_id)),
        (
            "relationship_suggestions",
            lambda: PostgresMentionRelationshipRepository(session=session).promote_to_candidates(dataset_id),
        ),
        ("email_domain_suggestions", lambda: propose_domain_affiliations(session, dataset_id)),
        ("event_links", lambda: resolve_event_links_workflow(session=session, dataset_id=dataset_id)),
        ("family_suggestions", lambda: propose_family_from_patronymics(session, dataset_id)),
        ("suggestions_closed", lambda: reconcile_resolved_name_groups(session, dataset_id)),
    ]
    if not link_selectors:
        steps = steps[1:]
    for done, (name, run) in enumerate(steps, start=1):
        counts[name] = await run()
        await progress("links", done, len(steps))
    return counts


async def resolution_workflow(
    session: AsyncSession,
    dataset_id: str,
    *,
    config: EntityResolutionConfig | None = None,
    link_selectors: bool = True,
    concurrency: int = 8,
    locations: bool = True,
    full: bool = False,
) -> dict:
    """Run the whole resolution stage for one dataset. Returns each step's counts.

    Auto-created entities are re-scored only when created since the last completed run
    (`full` re-scores them all).
    """
    engine = get_async_engine_from_settings()
    async with AsyncSession(engine, expire_on_commit=False) as run_session:
        runs = PostgresEnrichmentRunRepository(session=run_session)
        last = (
            None
            if full
            else await runs.latest_run(dataset_id=dataset_id, enrichment_type=RESOLUTION_RUN, status="completed")
        )
        await runs.close_interrupted_runs(enrichment_type=RESOLUTION_RUN, dataset_id=dataset_id)
        planned_id = os.environ.get(RUN_ID_ENV)
        if planned_id and await runs.adopt_run(planned_id, enrichment_type=RESOLUTION_RUN, device="na", unit="name"):
            run_id = planned_id
        else:
            run_id = await runs.start_run(
                enrichment_type=RESOLUTION_RUN,
                dataset_id=dataset_id,
                device="na",
                unit="name",
                params={"full": full, "concurrency": concurrency, "locations": locations},
            )
        progress = StepProgress(engine, run_id)
        try:
            async with keep_alive(engine, run_id):
                counts: dict = await resolve_entities_workflow(
                    session,
                    dataset_id,
                    config=config,
                    concurrency=concurrency,
                    entities_since=last.date_started if last else None,
                    report=progress,
                )
                if locations and default_gazetteer_path().exists():
                    counts["places"] = await resolve_locations_workflow(session=session, dataset_id=dataset_id)
                elif locations:
                    logger.warning(f"No gazetteer at {default_gazetteer_path()}; skipping location mentions")
                await progress("places", 1, 1)
                counts.update(await _links(session, dataset_id, link_selectors=link_selectors, progress=progress))
        except (asyncio.CancelledError, KeyboardInterrupt):
            await runs.finish_run(run_id, unit_count=0, status="stopped", error_message="interrupted")
            raise
        except Exception as exc:
            await runs.finish_run(
                run_id, unit_count=0, status="failed", error_message=f"{type(exc).__name__}: {exc}"[:2000]
            )
            raise
        await runs.finish_run(run_id, unit_count=counts["units"], status="completed")
    logger.success(f"Resolution stage for dataset {dataset_id}: {counts}")
    return counts
