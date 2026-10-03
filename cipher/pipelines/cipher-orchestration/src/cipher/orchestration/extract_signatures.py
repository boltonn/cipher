"""Signature affiliations: who the sender works for, in which unit, and how to reach them.

People put their employer, department, title and work contact details in their email
signature. This reads the sender's own signature in three steps (`docs/signatures.md`
walks through one email end to end):

1. **First pass (rules).** Skip Gmail bulk mail (promotions / updates / social / forums),
   cut the body at the first reply/forward marker, take the last `_TAIL_LINES` lines the
   sender wrote, and keep them as a *candidate* only when someone may sign off there
   (a farewell line, the sender's name or address, an NER person) **and** there is
   something to learn (an NER organization, a phone, a website, another email address)
   -- "Thanks, Nick" alone is never sent. The word lists live in `signature_cues.py`.
2. **Read (LLM).** The candidate goes to the local model (pyprompt `signature` pack),
   which decides whether it really ends in an individual's signature and, if so, copies
   it out verbatim: name, organization chain broadest-first (company -> division ->
   department), role, phones / emails / websites / addresses. A sender's signature,
   once read, is recognised in their later emails without another call.
3. **Check and emit.** Every value must appear verbatim; the signer must not be someone
   other than the sender (header name or address, `signer_agreement`); a brand signing as
   itself and a bare website given as "company" are dropped. Each value becomes a mention
   with offsets into the email, plus mention relations: person `employed_by` the most
   specific unit (`attributes.role`), each unit `part_of` the one above it, the company
   `located_in` each address. Phones / emails sit in the person's `field_path`, websites
   (as `domain` selectors) in the company's, so `resolve-entities` links them with
   `has_selector`. A sub-unit's resolution key is qualified by its company, so "Finance"
   at two companies never merges.

`resolve-entities` then resolves the names; the relations show as suggestions on the
organization page (name-level while names are unsettled). Enrichment-gated
(`signature_extraction`, needs `text_extraction`): each email is read once, failed model
calls are retried on the next run, and `reset-entities` / `--rebuild` clear it.
"""

import asyncio
import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import text
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresEntityRepository,
    PostgresExtractedTextRepository,
    PostgresMentionRelationshipRepository,
    PostgresMentionRepository,
)
from cipher.datastores.postgres.utils import normalize_name
from cipher.names import Level, address_name_agreement, compare_names, dominant_script, fold, to_latin, tokens
from cipher.orchestration.signature_cues import FAREWELLS, REPLY_MARKERS
from cipher.schemas.content.email import EmailMetadata
from cipher.schemas.graph.mention import MentionCreate, MentionedType
from cipher.schemas.graph.mention_relationship import MentionRelationshipCreate
from cipher.schemas.graph.ontology import EntityType, RelationshipType, SelectorType
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

EXTRACTOR = "signature"
PERSON_FIELD = "signature.person"
ADDRESS_FIELD = "signature.address"
_EMAIL_FILETYPE_GROUP = "email"
# The candidate: the last lines the sender wrote, capped so a long tail stays a small prompt.
_TAIL_LINES = 15
_MAX_TAIL_CHARS = 2000
_MAX_NAME_EXTRA_TOKENS = 2  # "Dr. Rosa Lindqvist, PhD"
_CONFIDENCE = {"match": 0.9, "neutral": 0.7}

_REPLY_MARKERS = re.compile(
    r"^\s*(?:" + "|".join(p for patterns in REPLY_MARKERS.values() for p in patterns) + ")",
    re.IGNORECASE | re.MULTILINE,
)
_FAREWELL_TRAILING = " \t,.!:;、，。！：؛،"
_PHONE = re.compile(r"(?<![\w+])\+?\d[\d\s().\-/]{7,}\d")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_WEBSITE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
# Gmail's bulk-mail categories (`file.source_tags`): newsletters and notifications, not people's signatures.
BULK_TAGS = frozenset({"promotions", "updates", "social", "forums"})
_FAREWELLS = frozenset(phrase.casefold() for phrases in FAREWELLS.values() for phrase in phrases)
_NAME_DECORATION = re.compile(r"^[\s\-–—_*~]+|[\s,*_~]+$")
_CCTLD_REGION = {"uk": "GB"}
_DOMAIN_ONLY = re.compile(r"^(?:https?://)?(?:www\.)?[\w-]+(?:\.[\w-]+)+/?$", re.IGNORECASE)


@dataclass(frozen=True)
class Span:
    text: str
    start: int
    end: int


class Cue(StrEnum):
    """Why the first pass kept an email's tail. A candidate needs a signer cue *and* a payload cue."""

    # signer: someone may be signing off here
    FAREWELL = "farewell"  # a line is a sign-off phrase from `signature_cues.FAREWELLS`
    SENDER_NAME = "sender_name"  # a line is the sender, by header name or address (`signer_agreement`)
    NER_PERSON = "ner_person"  # NER found a person in the tail
    # payload: there is something new to learn ("Thanks, Nick" alone has none)
    NER_ORGANIZATION = "ner_organization"  # NER found an organization in the tail
    SELECTOR = "selector"  # a phone number, a website, or an email address other than the sender's


SIGNER_CUES = frozenset({Cue.FAREWELL, Cue.SENDER_NAME, Cue.NER_PERSON})
PAYLOAD_CUES = frozenset({Cue.NER_ORGANIZATION, Cue.SELECTOR})


@dataclass(frozen=True)
class SignatureCandidate:
    """The last lines the sender wrote, kept because at least one cue fired."""

    text: str
    start: int
    cues: tuple[Cue, ...]

    @property
    def key(self) -> str:
        """Whitespace-insensitive hash of the candidate text."""
        return hashlib.sha1(" ".join(self.text.split()).encode()).hexdigest()


@dataclass(frozen=True)
class SignatureReading:
    """What the model read; every value is a string that occurs in the candidate."""

    is_signature: bool = False
    signature: str | None = None
    person_name: str | None = None
    organizations: list[str] = field(default_factory=list)
    role: str | None = None
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    websites: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SignatureAffiliation:
    """A reading grounded in one email body: absolute spans for everything that will become a mention."""

    person: Span
    units: list[Span]  # broadest first: company, division, department
    role: str | None
    phones: list[Span]
    emails: list[Span]
    websites: list[Span]
    addresses: list[Span]
    confidence: float
    context: str
    signer_is_sender: bool = False  # header name or address confirms the signer -- ties the sender's address to them


# ---- first pass ----------------------------------------------------------------------- #


def authored_text(body: str) -> str:
    """The part of an email body the sender wrote: everything above the first reply/forward marker."""
    marker = _REPLY_MARKERS.search(body)
    return body[: marker.start()] if marker else body


def _lines(text_: str, offset: int = 0) -> list[Span]:
    spans = []
    for raw in text_.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        stripped = line.strip()
        start = offset + (len(line) - len(line.lstrip()))
        spans.append(Span(stripped, start, start + len(stripped)))
        offset += len(raw)
    return spans


def is_farewell(line: str) -> bool:
    """The line is a sign-off phrase from `signature_cues.FAREWELLS` ("Best regards,", "С уважением")."""
    return line.strip().rstrip(_FAREWELL_TRAILING).casefold() in _FAREWELLS


class SignerAgreement(StrEnum):
    """Is a signature's signer the email's sender? Read from the header name and the address."""

    MATCH = "match"  # the address spells the signer's name, or the header name agrees (given name included)
    NEUTRAL = "neutral"  # nothing either way (`NB`, `bolton213@`), or the signals disagree
    CONFLICT = "conflict"  # the header or the address names someone else


def _header_name_agreement(signer: str, sender_name: str | None) -> SignerAgreement:
    """The header display name vs the signer: nickname- and script-tolerant, the given name must agree too."""
    sender_tokens = tokens(sender_name or "")
    if not sender_tokens:
        return SignerAgreement.NEUTRAL
    compact = to_latin(signer).replace(" ", "")
    if len(compact) >= 3 and compact == to_latin(sender_name).replace(" ", ""):  # 李娜 / Li Na
        return SignerAgreement.MATCH
    if len(sender_tokens) < 2:  # a bare "rosa" header proves nothing
        return SignerAgreement.NEUTRAL
    comparison = compare_names(sender_name, signer)
    given = comparison.components.get("given")
    if comparison.level >= Level.STRONG or (comparison.level == Level.MODERATE and given not in (None, "differ")):
        return SignerAgreement.MATCH
    # across writing systems a mismatch says little (田中 健二 romanizes to the Chinese reading, not "Tanaka")
    different_person = comparison.level == Level.CONFLICT or given == "differ"  # Edmond vs Nicholas Bolton
    if different_person and dominant_script(signer) == dominant_script(sender_name):
        return SignerAgreement.CONFLICT
    return SignerAgreement.NEUTRAL


def signer_agreement(signer: str, *, sender_name: str | None, sender_address: str | None) -> SignerAgreement:
    """Whether `signer` is the sender, from the header name and the sending address.

    The address is the stronger signal -- display names are often nicknames ("Nick B", "Coach N") --
    so an address that spells the signer's name wins; a matching header name counts unless the
    address spells someone else (a shared family mailbox).
    """
    signer = _NAME_DECORATION.sub("", signer)
    by_address = (
        SignerAgreement(address_name_agreement(sender_address, [signer]).value)
        if sender_address and "@" in sender_address
        else SignerAgreement.NEUTRAL
    )
    if by_address == SignerAgreement.MATCH:
        return SignerAgreement.MATCH
    by_name = _header_name_agreement(signer, sender_name)
    if by_name == SignerAgreement.MATCH:
        return SignerAgreement.NEUTRAL if by_address == SignerAgreement.CONFLICT else SignerAgreement.MATCH
    if SignerAgreement.CONFLICT in (by_name, by_address):
        return SignerAgreement.CONFLICT
    return SignerAgreement.NEUTRAL


def _is_name_line(line: str, *, sender_name: str | None, sender_address: str | None) -> bool:
    """A short line (a name, maybe "Dr." / ", PhD") that is the sender by header name or address."""
    line_tokens = tokens(line)
    if not line_tokens or len(line_tokens) > max(len(tokens(sender_name or "")), 3) + _MAX_NAME_EXTRA_TOKENS:
        return False
    return signer_agreement(line, sender_name=sender_name, sender_address=sender_address) == SignerAgreement.MATCH


def find_candidate(
    body: str,
    *,
    sender_name: str | None,
    sender_address: str | None = None,
    ner_spans: list[tuple[EntityType, int]] = (),
) -> SignatureCandidate | None:
    """The last lines the sender wrote, if someone may sign off there *and* there is something to learn.

    Signer cues: a farewell line, the sender's name / address on a line, an NER person. Payload
    cues: an NER organization, a phone number, a website, an email address other than the
    sender's. `ner_spans` are `(entity_type, start_offset)` of NER mentions in `body`, when an
    NER pass has run; without them the other cues still apply.
    """
    lines = [line for line in _lines(authored_text(body)) if line.text][-_TAIL_LINES:]
    while len(lines) > 1 and lines[-1].end - lines[0].start > _MAX_TAIL_CHARS:
        lines = lines[1:]
    if not lines:
        return None
    start, end = lines[0].start, lines[-1].end
    tail = body[start:end]
    found = {entity_type for entity_type, offset in ner_spans if start <= offset < end}
    other_emails = {email.lower() for email in _EMAIL.findall(tail)} - {(sender_address or "").lower()}
    cues = [
        cue
        for cue, fired in (
            (Cue.FAREWELL, any(is_farewell(line.text) for line in lines)),
            (
                Cue.SENDER_NAME,
                bool(sender_name or sender_address)
                and any(
                    _is_name_line(line.text, sender_name=sender_name, sender_address=sender_address) for line in lines
                ),
            ),
            (Cue.NER_PERSON, EntityType.PERSON in found),
            (Cue.NER_ORGANIZATION, EntityType.ORGANIZATION in found),
            (
                Cue.SELECTOR,
                bool(
                    _PHONE.search(tail)
                    or _WEBSITE.search(tail)
                    or other_emails
                    or any(_DOMAIN_ONLY.match(line.text) for line in lines)  # a bare `fourthbrain.ai` line
                ),
            ),
        )
        if fired
    ]
    if not (SIGNER_CUES.intersection(cues) and PAYLOAD_CUES.intersection(cues)):
        return None
    return SignatureCandidate(text=tail, start=start, cues=tuple(cues))


# ---- grounding ------------------------------------------------------------------------ #


def _locate(region: Span, value: str | None) -> Span | None:
    """`value`'s absolute span inside `region` -- exact, case-insensitive, or with inflected endings."""
    from pyprompt.offsets import find_span

    span = find_span(region.text, value)
    if span is None:
        return None
    start = region.start + span[0]
    return Span(region.text[span[0] : span[1]], start, region.start + span[1])


def _squash(text_: str) -> str:
    return "".join(ch for ch in fold(text_) if ch.isalnum())


def is_organization_signer(person: str, units: list[str]) -> bool:
    """The "signer" is the organization itself: `Kaggle` from Kaggle, `The Microsoft account team`.

    The name equals a unit or a unit makes up most of it -- a brand mailbox, not a person. A surname
    that happens to be the company (`Henry Ford` at `Ford`) is a small part of the name and stays.
    """
    name = _squash(person)
    return bool(name) and any(
        unit and (unit == name or (unit in name and len(unit) * 2 >= len(name))) for unit in (_squash(u) for u in units)
    )


def ground(
    candidate: SignatureCandidate,
    reading: SignatureReading,
    *,
    sender_name: str | None,
    sender_address: str | None = None,
) -> SignatureAffiliation | None:
    """Pin a reading to the email's offsets, or None when it isn't the sender's affiliation.

    Values are located inside the signature the model copied out (else the whole candidate).
    Needs a person and at least one organization; drops a signer the header name or address
    says is someone else, a brand signing as itself, and a bare website given as a "company".
    """
    if not reading.is_signature:
        return None
    whole = Span(candidate.text, candidate.start, candidate.start + len(candidate.text))
    region = _locate(whole, reading.signature) or whole
    # a bare domain (`fourthbrain.ai`) is the website, not the organization's name
    units = [u for u in (_locate(region, o) for o in reading.organizations) if u and not _DOMAIN_ONLY.match(u.text)]
    person = _locate(region, _NAME_DECORATION.sub("", reading.person_name or ""))
    if not units or person is None or is_organization_signer(person.text, [u.text for u in units]):
        return None
    agreement = signer_agreement(person.text, sender_name=sender_name, sender_address=sender_address)
    if agreement == SignerAgreement.CONFLICT:
        return None

    def spans(values: list[str]) -> list[Span]:
        return [s for s in (_locate(region, v) for v in values) if s]

    return SignatureAffiliation(
        person=person,
        units=units,
        role=reading.role,
        phones=spans(reading.phones),
        emails=spans(reading.emails),
        websites=spans(reading.websites),
        addresses=spans(reading.addresses),
        confidence=_CONFIDENCE[agreement.value],
        context=region.text,
        signer_is_sender=agreement == SignerAgreement.MATCH,
    )


# ---- emission ------------------------------------------------------------------------- #


def _region_hint(address: str | None) -> str | None:
    """A phone region from the sender's country-code TLD (`.de` -> DE), for numbers written without `+`."""
    tld = (address or "").rsplit(".", 1)[-1].lower()
    return _CCTLD_REGION.get(tld, tld.upper()) if len(tld) == 2 else None


@dataclass
class _Emitter:
    session: "AsyncSession"
    dataset_id: str
    counts: dict[str, int]

    def __post_init__(self):
        self.mentions = PostgresMentionRepository(session=self.session)
        self.relations = PostgresMentionRelationshipRepository(session=self.session)
        self.entities = PostgresEntityRepository(session=self.session)

    def _name(
        self, *, text_id, file_id, span: Span, entity_type, field_path, context, confidence, key=None, attribute="name"
    ):
        return MentionCreate(
            dataset_id=self.dataset_id,
            mentioned_type=MentionedType.EXTRACTED_TEXT,
            mentioned_id=text_id,
            file_id=file_id,
            surface_text=span.text,
            entity_type=entity_type,
            entity_attribute=attribute,
            normalized_value=normalize_name(key or span.text),
            start_offset=span.start,
            end_offset=span.end,
            field_path=field_path,
            context=context,
            extractor=EXTRACTOR,
            extraction_confidence=confidence,
        )

    async def _selectors(
        self,
        *,
        text_id,
        file_id,
        spans,
        selector_type,
        field_path,
        region,
        context,
        mentioned_type: MentionedType = MentionedType.EXTRACTED_TEXT,
    ) -> int:
        from pyselectors.normalize import normalize_selector

        rows = []
        for span in spans:
            normalized, _ = normalize_selector(selector_type, span.text, region)
            if not normalized:
                continue
            entity, _ = await self.entities.get_or_create_selector(
                dataset_id=self.dataset_id,
                selector_type=selector_type,
                raw_value=span.text,
                normalized_value=normalized,
            )
            rows.append(
                MentionCreate(
                    dataset_id=self.dataset_id,
                    entity_id=entity.id,
                    mentioned_type=mentioned_type,
                    mentioned_id=text_id,
                    file_id=file_id,
                    surface_text=span.text,
                    entity_type=EntityType.SELECTOR,
                    entity_attribute="value",
                    selector_type=selector_type,
                    normalized_value=normalized,
                    start_offset=span.start if span.start >= 0 else None,
                    end_offset=span.end if span.end >= 0 else None,
                    field_path=field_path,
                    context=context,
                    extractor=EXTRACTOR,
                    extraction_confidence=1.0,
                )
            )
        await self.mentions.add_mentions_batch(rows)
        return len(rows)

    async def emit(self, found: SignatureAffiliation, *, text_id: str, file_id: str, sender_address: str | None):
        common = dict(text_id=text_id, file_id=file_id, context=found.context, confidence=found.confidence)
        company = found.units[0].text
        rows = [self._name(span=found.person, entity_type=EntityType.PERSON, field_path=PERSON_FIELD, **common)]
        for index, unit in enumerate(found.units):
            rows.append(
                self._name(
                    span=unit,
                    entity_type=EntityType.ORGANIZATION,
                    field_path=f"signature.unit.{index}",
                    # a sub-unit resolves within its company: "Finance" at two companies never merges
                    key=unit.text if index == 0 else f"{company} / {unit.text}",
                    **common,
                )
            )
        for address in found.addresses:
            rows.append(
                self._name(
                    span=address,
                    entity_type=EntityType.LOCATION,
                    field_path=ADDRESS_FIELD,
                    attribute="address",
                    **common,
                )
            )
        person, *rest = await self.mentions.add_mentions_returning(rows)
        units, addresses = rest[: len(found.units)], rest[len(found.units) :]

        relation = dict(
            dataset_id=self.dataset_id,
            confidence=found.confidence,
            file_id=file_id,
            context=found.context,
            extractor=EXTRACTOR,
        )
        relations = [
            MentionRelationshipCreate(
                src_mention_id=person.id,
                dst_mention_id=units[-1].id,
                relationship_type=RelationshipType.EMPLOYED_BY,
                attributes={"role": found.role} if found.role else {},
                **relation,
            ),
            *(
                MentionRelationshipCreate(
                    src_mention_id=child.id,
                    dst_mention_id=parent.id,
                    relationship_type=RelationshipType.PART_OF,
                    **relation,
                )
                for parent, child in zip(units, units[1:], strict=False)
            ),
            *(
                MentionRelationshipCreate(
                    src_mention_id=units[0].id,
                    dst_mention_id=address.id,
                    relationship_type=RelationshipType.LOCATED_IN,
                    **relation,
                )
                for address in addresses
            ),
        ]
        await self.relations.add_batch(relations)

        region = _region_hint(sender_address)
        selector = dict(text_id=text_id, file_id=file_id, region=region, context=found.context)
        self.counts["selectors"] += await self._selectors(
            spans=found.phones, selector_type=SelectorType.PHONE, field_path=PERSON_FIELD, **selector
        )
        self.counts["selectors"] += await self._selectors(
            spans=found.emails, selector_type=SelectorType.EMAIL, field_path=PERSON_FIELD, **selector
        )
        if found.signer_is_sender and sender_address:
            # the confirmed signer owns the sending address: resolution links them (has_selector)
            self.counts["selectors"] += await self._selectors(
                spans=[Span(sender_address, -1, -1)],
                selector_type=SelectorType.EMAIL,
                field_path=PERSON_FIELD,
                mentioned_type=MentionedType.STRUCTURED_FIELD,
                **selector,
            )
        self.counts["selectors"] += await self._selectors(
            spans=found.websites, selector_type=SelectorType.DOMAIN, field_path="signature.unit.0", **selector
        )
        self.counts["signatures"] += 1
        self.counts["sub_units"] += len(found.units) - 1
        self.counts["with_role"] += bool(found.role)
        self.counts["addresses"] += len(found.addresses)


def _sender_label(sender) -> str:
    return " ".join(p for p in (sender.name, f"<{sender.value}>") if p)


def _llm_reader(model: str | None) -> Callable[[SignatureCandidate, str | None], Awaitable[SignatureReading]]:
    from pyprompt import PromptRunner, Settings

    runner = PromptRunner(Settings())

    async def read(candidate: SignatureCandidate, sender: str | None) -> SignatureReading:
        out = await runner.read_signature(candidate.text, sender=sender, model=model)
        return SignatureReading(**out.model_dump())

    return read


class _ReadingCache:
    """Readings by candidate text, plus each sender's known signatures -- recognised in later emails."""

    def __init__(self):
        self.by_key: dict[tuple[str, str], SignatureReading] = {}
        self.by_sender: dict[str, list[tuple[str, SignatureReading]]] = {}

    @staticmethod
    def _squeeze(text_: str) -> str:
        return " ".join(text_.split())

    def get(self, sender: str, candidate: SignatureCandidate) -> SignatureReading | None:
        if (hit := self.by_key.get((sender, candidate.key))) is not None:
            return hit
        squeezed = self._squeeze(candidate.text)
        return next((r for signature, r in self.by_sender.get(sender, []) if signature in squeezed), None)

    def put(self, sender: str, candidate: SignatureCandidate, reading: SignatureReading) -> None:
        self.by_key[(sender, candidate.key)] = reading
        if reading.is_signature and reading.signature:
            self.by_sender.setdefault(sender, []).append((self._squeeze(reading.signature), reading))


_RESET_STATEMENTS = (
    # auto-created entities only signature mentions point at (verified/manual ones are kept)
    """DELETE FROM entity e WHERE e.dataset_id = :dataset_id AND NOT e.is_verified AND e.source <> 'MANUAL'
       AND e.person_id IS NULL AND e.location_id IS NULL AND e.entity_type <> 'SELECTOR'
       AND EXISTS (SELECT 1 FROM mention m WHERE m.entity_id = e.id AND m.extractor = :extractor)
       AND NOT EXISTS (SELECT 1 FROM mention m WHERE m.entity_id = e.id AND m.extractor IS DISTINCT FROM :extractor)""",
    """DELETE FROM entity_relationship_candidate WHERE dataset_id = :dataset_id AND status = 'PENDING'
       AND method = 'SIGNATURE'""",
    "DELETE FROM mention_relationship WHERE dataset_id = :dataset_id AND extractor = :extractor",
    "DELETE FROM mention WHERE dataset_id = :dataset_id AND extractor = :extractor",
)

_NER_SPANS = text(
    """
    SELECT file_id, entity_type, start_offset FROM mention
    WHERE file_id = ANY(CAST(:file_ids AS text[])) AND extractor IS DISTINCT FROM :extractor
      AND entity_type IN ('PERSON', 'ORGANIZATION') AND mentioned_type = 'EXTRACTED_TEXT'
      AND start_offset IS NOT NULL
    """
)


async def reset_signatures(session: "AsyncSession", dataset_id: str) -> None:
    """Drop this workflow's output for a dataset so the next run re-reads every email.

    Removes signature mentions and relations, pending signature suggestions, and the
    auto-created entities nothing but signatures pointed at -- the rest of the entity
    layer (and any reviewed decision) is untouched.
    """
    for statement in _RESET_STATEMENTS:
        await session.execute(text(statement), {"dataset_id": dataset_id, "extractor": EXTRACTOR})
    await PostgresEnrichmentRepository(session=session).delete_by_type(dataset_id, EnrichmentType.SIGNATURE_EXTRACTION)
    await session.commit()


async def extract_signatures_workflow(
    session: "AsyncSession",
    dataset_id: str,
    *,
    concurrency: int = 8,
    model: str | None = None,
    batch_size: int = 200,
    limit: int | None = None,
    rebuild: bool = False,
    include_bulk: bool = False,
) -> dict[str, int]:
    """Read each sender's signature into person / unit-chain / role / selector mentions and relations.

    Enrichment-gated like every analytic: each email gets one `signature_extraction` row,
    completed whether or not it had a signature, failed (and retried next run) when the
    model call fails. Emails Gmail tagged as bulk (`BULK_TAGS`) are skipped unless `include_bulk`.
    """
    if rebuild:
        await reset_signatures(session, dataset_id)
    enrichments = PostgresEnrichmentRepository(session=session)
    await enrichments.queue_enrichments_by_filter(
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.SIGNATURE_EXTRACTION,
        filetype_group=_EMAIL_FILETYPE_GROUP,
    )
    await session.commit()
    texts = PostgresExtractedTextRepository(session=session)
    counts = dict.fromkeys(
        (
            "emails",
            "skipped_bulk",
            "failed",
            "candidates",
            *(f"cue_{cue.value}" for cue in Cue),
            "llm_calls",
            "reused",
            "signatures",
            "sub_units",
            "with_role",
            "selectors",
            "addresses",
        ),
        0,
    )
    emitter = _Emitter(session=session, dataset_id=dataset_id, counts=counts)
    llm_read = _llm_reader(model)
    cache = _ReadingCache()
    semaphore = asyncio.Semaphore(concurrency)

    async def read(sender, candidate: SignatureCandidate) -> SignatureReading | Exception:
        async with semaphore:
            try:
                reading = await llm_read(candidate, _sender_label(sender))
            except Exception as exc:
                logger.warning(f"Signature read failed ({sender.value}): {exc}")
                return exc
        counts["llm_calls"] += 1
        cache.put(sender.value.lower(), candidate, reading)
        return reading

    pending_filter = dict(
        enrichment_type=EnrichmentType.SIGNATURE_EXTRACTION,
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        filetype_group_filter=_EMAIL_FILETYPE_GROUP,
    )
    total = await enrichments.count_pending(**pending_filter)
    with tqdm(total=min(total, limit or total), desc="Reading signatures", unit=" email") as progress:
        while limit is None or counts["emails"] < limit:
            size = batch_size if limit is None else min(batch_size, limit - counts["emails"])
            batch = await enrichments.get_pending_batch(batch_size=size, **pending_filter)
            if not batch:
                break
            await enrichments.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
            await session.commit()

            bulk = {
                item.resource["id"]
                for item in batch
                if not include_bulk and BULK_TAGS.intersection(item.resource.get("source_tags") or [])
            }
            counts["skipped_bulk"] += len(bulk)
            file_ids = [item.resource["id"] for item in batch if item.resource["id"] not in bulk]
            by_file = await texts.get_by_file_ids(file_ids)
            ner: dict[str, list[tuple[EntityType, int]]] = {}
            for file_id, entity_type, offset in (
                await session.execute(_NER_SPANS, {"file_ids": file_ids, "extractor": EXTRACTOR})
            ).all():
                ner.setdefault(file_id, []).append((EntityType[entity_type], offset))

            candidates = []
            for file_id, extracted in by_file.items():
                metadata = extracted.metadata
                sender = (metadata.sent_from or metadata.sender) if isinstance(metadata, EmailMetadata) else None
                if sender is None:
                    continue
                candidate = find_candidate(
                    extracted.content,
                    sender_name=sender.name,
                    sender_address=sender.value,
                    ner_spans=ner.get(file_id, []),
                )
                if candidate is not None:
                    candidates.append((file_id, extracted, sender, candidate))
                    for cue in candidate.cues:
                        counts[f"cue_{cue.value}"] += 1
            counts["candidates"] += len(candidates)

            # one call per sender first, so their later emails can reuse the signature it finds
            readings: dict[str, SignatureReading | Exception] = {}
            for wave in range(2):
                todo, seen_senders = [], set()
                for file_id, _, sender, candidate in candidates:
                    if file_id in readings:
                        continue
                    if (hit := cache.get(sender.value.lower(), candidate)) is not None:
                        readings[file_id] = hit
                        counts["reused"] += 1
                    elif wave == 1 or sender.value.lower() not in seen_senders:
                        seen_senders.add(sender.value.lower())
                        todo.append((file_id, sender, candidate))
                results = await asyncio.gather(*(read(sender, candidate) for _, sender, candidate in todo))
                readings.update({file_id: result for (file_id, _, _), result in zip(todo, results, strict=True)})

            failed_files: dict[str, Exception] = {}
            for file_id, extracted, sender, candidate in candidates:
                reading = readings[file_id]
                if isinstance(reading, Exception):
                    failed_files[file_id] = reading
                    continue
                found = ground(candidate, reading, sender_name=sender.name, sender_address=sender.value)
                if found is not None:
                    await emitter.emit(found, text_id=extracted.id, file_id=file_id, sender_address=sender.value)

            await enrichments.mark_completed_batch(
                [item.enrichment.id for item in batch if item.resource["id"] not in failed_files]
            )
            await enrichments.mark_failed(
                {
                    item.enrichment.id: failed_files[item.resource["id"]]
                    for item in batch
                    if item.resource["id"] in failed_files
                }
            )
            await session.commit()
            counts["emails"] += len(batch)
            counts["failed"] += len(failed_files)
            progress.update(len(batch))
    logger.success(f"Signatures for dataset {dataset_id}: {counts}")
    return counts
