"""Find earlier messages quoted inside an email's text -- reply history and forwards, in any language.

Mail clients introduce a quoted message one of four ways, each localized:
an attribution line ("On <date>, <name> <addr> wrote:"), a separator line
("-----Original Message-----", "---------- Forwarded message ---------"), an
Outlook header block ("From: ... / Sent: ..."), or ``>``-prefixed lines. Each
start opens a block that runs to the next start or the end of the text -- unless
its first lines are ``>``-quoted, in which case it ends with them (the writer
answered below the quote).
"""

import re
from datetime import datetime
from email.utils import parseaddr
from typing import Final

from cipher.schemas.content.email import QuotedBlock, QuoteKind


def _alternation(words: list[str]) -> str:
    return "|".join(sorted((re.escape(word) for word in words), key=len, reverse=True))


# Words that open a reply attribution ("On ...", "Le ...", "Am ...", "在 ...", "في ...").
_REPLY_LEADS: Final[str] = _alternation(
    ["On", "Le", "El", "Am", "Em", "Il", "Op", "Den", "På", "W dniu", "Dne", "在", "於", "في", "در"]
)
# The verb that ends one ("wrote", "a écrit", "написал(а)", "写道", "كتب", "نوشت", ...).
_REPLY_VERBS: Final[str] = _alternation(
    [
        "wrote",
        "writes",
        "a écrit",
        "escribió",
        "schrieb",
        "escreveu",
        "ha scritto",
        "schreef",
        "skrev",
        "napisał(a)",
        "napisał",
        "napisała",
        "napsal",
        "написал(а)",
        "написала",
        "написал",
        "пишет",
        "написав(ла)",
        "написала",
        "написав",
        "пише",
        "写道",
        "寫道",
        "كتب",
        "نوشت",
        "書きました",
        "작성",
        "yazdı",
    ]
)
_SEPARATOR_FORWARD: Final[list[str]] = [
    "Forwarded message",
    "Forwarded Message",
    "Message transféré",
    "Mensaje reenviado",
    "Weitergeleitete Nachricht",
    "Doorgestuurd bericht",
    "Messaggio inoltrato",
    "Mensagem encaminhada",
    "Пересылаемое сообщение",
    "Пересланное сообщение",
    "Переслане повідомлення",
    "转发的邮件",
    "已转发邮件",
    "轉寄的郵件",
    "رسالة معاد توجيهها",
    "پیام بازارسال شده",
    "پیام هدایت شده",
    "転送されたメッセージ",
    "전달된 메시지",
    "İletilen ileti",
]
_SEPARATOR_REPLY: Final[list[str]] = [
    "Original Message",
    "Message d'origine",
    "Message d’origine",
    "Mensaje original",
    "Ursprüngliche Nachricht",
    "Oorspronkelijk bericht",
    "Messaggio originale",
    "Mensagem original",
    "Исходное сообщение",
    "Оригинальное сообщение",
    "Вихідне повідомлення",
    "Оригінальне повідомлення",
    "原始邮件",
    "原始郵件",
    "الرسالة الأصلية",
    "پیام اصلی",
    "元のメッセージ",
    "원본 메시지",
    "Orijinal ileti",
]
_APPLE_FORWARD: Final[list[str]] = [
    "Begin forwarded message",
    "Début du message réexpédié",
    "Inicio del mensaje reenviado",
    "Anfang der weitergeleiteten Nachricht",
    "Inizio messaggio inoltrato",
    "Início da mensagem reencaminhada",
    "Начало переадресованного сообщения",
    "Початок пересланого повідомлення",
    "转发的邮件",
    "転送されたメッセージ",
]
_FROM_LABELS: Final[str] = _alternation(
    [
        "From",
        "De",
        "Von",
        "Van",
        "Da",
        "Fra",
        "Från",
        "Od",
        "От",
        "Від",
        "Kimden",
        "Gönderen",
        "发件人",
        "寄件者",
        "差出人",
        "보낸 사람",
        "من",
        "از",
    ]
)
_SENT_LABELS: Final[str] = _alternation(
    [
        "Sent",
        "Date",
        "Envoyé",
        "Gesendet",
        "Datum",
        "Verzonden",
        "Inviato",
        "Data",
        "Enviado",
        "Enviada",
        "Fecha",
        "Отправлено",
        "Дата",
        "Надіслано",
        "Tarih",
        "Gönderildi",
        "发送时间",
        "日期",
        "時間",
        "寄件日期",
        "送信日時",
        "日付",
        "보낸 날짜",
        "날짜",
        "أرسلت",
        "التاريخ",
        "تاريخ",
        "ارسال شده",
        "تاریخ",
    ]
)
_SUBJECT_LABELS: Final[str] = _alternation(
    [
        "Subject",
        "Objet",
        "Betreff",
        "Onderwerp",
        "Oggetto",
        "Asunto",
        "Assunto",
        "Тема",
        "Konu",
        "主题",
        "主旨",
        "件名",
        "제목",
        "الموضوع",
        "موضوع",
    ]
)

_DIRECTION_MARKS: Final[str] = "‎‏‪‫‬"
_COLON: Final[str] = r"\s*[:：]"
_LEAD_RE: Final[re.Pattern[str]] = re.compile(rf"^[{_DIRECTION_MARKS}\s]*(?:{_REPLY_LEADS})\s", re.IGNORECASE)
_ATTRIBUTION_END_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?:(?:{_REPLY_VERBS})[^\n:：]{{0,120}}|<[^<>\s@]+@[^<>\s]+>){_COLON}[\s{_DIRECTION_MARKS}]*$", re.IGNORECASE
)
_SEPARATOR_RE: Final[re.Pattern[str]] = re.compile(
    rf"^[\s>]*-{{2,}}\s*(?:(?P<forward>{_alternation(_SEPARATOR_FORWARD)})|(?P<reply>{_alternation(_SEPARATOR_REPLY)}))\s*-{{2,}}\s*$",
    re.IGNORECASE,
)
_APPLE_FORWARD_RE: Final[re.Pattern[str]] = re.compile(
    rf"^\s*(?:{_alternation(_APPLE_FORWARD)}){_COLON}\s*$", re.IGNORECASE
)
_RULE_RE: Final[re.Pattern[str]] = re.compile(r"^\s*_{10,}\s*$")
_FROM_RE: Final[re.Pattern[str]] = re.compile(
    rf"^[\s>*]*(?:{_FROM_LABELS})\*?{_COLON}\s*(?P<value>\S.*)$", re.IGNORECASE
)
_SENT_RE: Final[re.Pattern[str]] = re.compile(
    rf"^[\s>*]*(?:{_SENT_LABELS})\*?{_COLON}\s*(?P<value>\S.*)$", re.IGNORECASE
)
_SUBJECT_RE: Final[re.Pattern[str]] = re.compile(
    rf"^[\s>*]*(?:{_SUBJECT_LABELS})\*?{_COLON}\s*(?P<value>.*)$", re.IGNORECASE
)
_FORWARD_SUBJECT_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:fwd?|tr|wg|rv|enc|doorst|пересл|переслать|转发|轉寄)\s*[:：]", re.IGNORECASE
)
_WRAPPED_ADDRESS_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:\[mailto:|<)[^\s@]+@\S+\s*$")
_ANGLE_QUOTE_RE: Final[re.Pattern[str]] = re.compile(r"^[ \t]*>(?!=)")  # not a `>= 1.2` version range
_ADDRESS_RE: Final[re.Pattern[str]] = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
_NAME_SPLIT_RE: Final[re.Pattern[str]] = re.compile(
    rf"[,，]|\s(?:at|à|a las|um|в|о)\s|\d{{1,2}}[:.]\d{{2}}(?:[:.]\d{{2}})?(?:\s?[AaPp]\.?\s?[Mm]\.?)?|(?:{_REPLY_VERBS})",
    re.IGNORECASE,
)
_MONTHS: Final[dict[str, int]] = {
    m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)
}
_TIME: Final[str] = r"(?:,?\s*(?:at\s+)?(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::\d{2})?\s*(?P<ampm>[AaPp]\.?[Mm]\.?)?)?"
_MONTH_FIRST_RE: Final[re.Pattern[str]] = re.compile(
    rf"\b(?P<month>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?P<day>\d{{1,2}}),?\s+(?P<year>\d{{4}}){_TIME}",
    re.IGNORECASE,
)
_DAY_FIRST_RE: Final[re.Pattern[str]] = re.compile(
    rf"\b(?P<day>\d{{1,2}})\s+(?P<month>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(?P<year>\d{{4}}){_TIME}",
    re.IGNORECASE,
)
_CLOCK_RE: Final[re.Pattern[str]] = re.compile(r"\d{1,2}[:.]\d{2}")
_MAX_ATTRIBUTION_LINES: Final[int] = 3
_MAX_ATTRIBUTION_CHARS: Final[int] = 400
_MAX_HEADER_GAP: Final[int] = 4
_MIN_BARE_QUOTE_LINES: Final[int] = 2  # a lone "> Register" is a button arrow, not a quote


def find_quoted_blocks(text: str) -> list[QuotedBlock]:
    """Every earlier message quoted in `text`, in order.

    Args:
        text: An email's extracted text.

    Returns:
        One block per quoted message; empty when the email quotes nothing.
    """
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    stripped = [line.rstrip("\r\n") for line in lines]

    starts: list[tuple[int, int, QuoteKind, dict]] = []  # (first line, last header line, kind, header fields)
    covered_until = -1
    for index, line in enumerate(stripped):
        if index <= covered_until:
            continue
        found = _separator_at(stripped, index) or _header_block_at(stripped, index) or _attribution_at(stripped, index)
        if found:
            starts.append(found)
            covered_until = found[1]
        elif _ANGLE_QUOTE_RE.match(line) and not (starts and _inside_last(starts, stripped, index)):
            run_end = _angle_run_end(stripped, index)
            if (
                sum(bool(_ANGLE_QUOTE_RE.match(quoted)) for quoted in stripped[index : run_end + 1])
                >= _MIN_BARE_QUOTE_LINES
            ):
                starts.append((index, index - 1, QuoteKind.REPLY, {}))
            covered_until = run_end

    blocks = []
    for position, (first, header_end, kind, fields) in enumerate(starts):
        next_first = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        body_start = next((i for i in range(header_end + 1, next_first) if stripped[i].strip()), next_first)
        last = (
            _angle_run_end(stripped, body_start)
            if body_start < next_first and _ANGLE_QUOTE_RE.match(stripped[body_start])
            else next_first - 1
        )
        attribution = "\n".join(stripped[first : header_end + 1]).strip() or None
        name, address = fields.get("from_name"), fields.get("from_address")
        if attribution and not fields:
            name, address = _author_from_attribution(attribution)
        end = offsets[last + 1]
        while end > offsets[first] and text[end - 1].isspace():
            end -= 1
        blocks.append(
            QuotedBlock(
                start_offset=offsets[first],
                end_offset=end,
                kind=kind,
                attribution=attribution,
                from_name=name,
                from_address=address,
                date_sent=_parse_date(fields.get("date") or attribution or ""),
            )
        )
    return blocks


def _separator_at(lines: list[str], index: int) -> tuple[int, int, QuoteKind, dict] | None:
    """A separator line, a forward intro, or an Outlook rule -- with the header block under it."""
    line = lines[index]
    if match := _SEPARATOR_RE.match(line):
        kind = QuoteKind.FORWARD if match["forward"] else QuoteKind.REPLY
    elif _APPLE_FORWARD_RE.match(line):
        kind = QuoteKind.FORWARD
    elif _RULE_RE.match(line):
        header = _header_block_at(lines, _next_nonblank(lines, index + 1))
        return (index, header[1], header[2], header[3]) if header else None
    else:
        return None
    header = _header_block_at(lines, _next_nonblank(lines, index + 1), require_sent=False)
    if header:
        return index, header[1], QuoteKind.FORWARD if kind == QuoteKind.FORWARD else header[2], header[3]
    return index, index, kind, {}


def _header_block_at(
    lines: list[str], index: int, *, require_sent: bool = True
) -> tuple[int, int, QuoteKind, dict] | None:
    """An Outlook/Gmail header block ("From: ..." then "Sent: ..."/"Subject: ..." within a few lines)."""
    if index >= len(lines) or not (from_match := _FROM_RE.match(lines[index])):
        return None
    fields: dict = {}
    value, last = from_match["value"], index
    if index + 1 < len(lines) and _WRAPPED_ADDRESS_RE.match(lines[index + 1]):
        value, last = f"{value} {lines[index + 1].strip()}", index + 1
    fields["from_name"], fields["from_address"] = _parse_from(value)
    subject, has_sent, position = "", False, last
    for _ in range(_MAX_HEADER_GAP + 1):
        position += 1
        if position < len(lines) and not lines[position].strip() and position == last + 1:
            position += 1  # HTML mail puts each header line in its own paragraph
        if position >= len(lines) or not lines[position].strip():
            break
        if sent := _SENT_RE.match(lines[position]):
            fields["date"], has_sent, last = sent["value"], True, position
        elif subject_match := _SUBJECT_RE.match(lines[position]):
            subject, last = subject_match["value"], position
        elif re.match(r"^[\s>*]*[^\s:：]{1,20}\*?\s*[:：]", lines[position]):
            last = position  # To / Cc / Importance in any language
        else:
            break
    if require_sent and not has_sent:
        return None
    kind = QuoteKind.FORWARD if _FORWARD_SUBJECT_RE.match(subject) else QuoteKind.REPLY
    return index, last, kind, fields


def _attribution_at(lines: list[str], index: int) -> tuple[int, int, QuoteKind, dict] | None:
    """A reply attribution ending on this line or up to two lines below (clients wrap long ones)."""
    for last in range(index, min(index + _MAX_ATTRIBUTION_LINES, len(lines))):
        if not lines[last].strip():
            return None
        if _ATTRIBUTION_END_RE.search(lines[last]):
            attribution = " ".join(lines[index : last + 1])
            has_address = bool(_ADDRESS_RE.search(attribution))
            has_digit = any(character.isdigit() for character in attribution)
            leads = bool(_LEAD_RE.match(lines[index]))
            has_time = bool(_CLOCK_RE.search(attribution))
            looks_like_attribution = (leads and (has_digit or has_address)) or (
                last == index and (has_address or has_time)
            )
            if looks_like_attribution and len(attribution) <= _MAX_ATTRIBUTION_CHARS:
                return index, last, QuoteKind.REPLY, {}
            return None
    return None


def _inside_last(starts: list[tuple[int, int, QuoteKind, dict]], lines: list[str], index: int) -> bool:
    """Whether a `>` line directly continues the latest block (its quote, not a new one)."""
    previous = next((i for i in range(index - 1, -1, -1) if lines[i].strip()), -1)
    return previous == starts[-1][1] or (previous >= starts[-1][0] and bool(_ANGLE_QUOTE_RE.match(lines[previous])))


def _angle_run_end(lines: list[str], index: int) -> int:
    """Last line of the `>`-quoted run starting at `index` (blank lines inside the run are part of it)."""
    last = index
    for position in range(index, len(lines)):
        if _ANGLE_QUOTE_RE.match(lines[position]):
            last = position
        elif lines[position].strip():
            break
    return last


def _next_nonblank(lines: list[str], index: int) -> int:
    return next((i for i in range(index, len(lines)) if lines[i].strip()), len(lines))


def _parse_from(value: str) -> tuple[str | None, str | None]:
    """`Megan Flick <m@x.com>`, `Megan Flick [mailto:m@x.com]`, `"Flick, Megan"`, or a bare address."""
    value = re.sub(r"\[mailto:([^\]]+)\]", r"<\1>", value.strip().strip("*"))
    name, address = parseaddr(value)
    address = address if _ADDRESS_RE.fullmatch(address or "") else None
    if address is None and (found := _ADDRESS_RE.search(value)):
        address = found.group(0)
        name = value.replace(found.group(0), "").strip(" <>\"'")
    name = (name or "").strip(" \"'") or (None if address else value.strip(" \"'") or None)
    return name, address.lower() if address else None


def _author_from_attribution(attribution: str) -> tuple[str | None, str | None]:
    """The quoted author in "On <date>, Megan Flick <m@x.com> wrote:" and its localized forms."""
    flat = " ".join(attribution.split()).strip(_DIRECTION_MARKS)
    address_match = _ADDRESS_RE.search(flat)
    address = address_match.group(0).lower() if address_match else None
    head = flat[: flat.find("<")] if "<" in flat else flat
    if not address_match:
        head = re.split(rf"(?:{_REPLY_VERBS}){_COLON}", head, flags=re.IGNORECASE)[0]
    pieces = [piece for piece in _NAME_SPLIT_RE.split(head) if piece and piece.strip()]
    name = (
        re.sub(rf"^(?:{_REPLY_LEADS})\s+", "", pieces[-1].strip(), flags=re.IGNORECASE).strip(" \"'()[]")
        if pieces
        else ""
    )
    if not name or re.search(r"\d", name) or "@" in name or len(name.split()) > 6:
        name = ""
    return name or None, address


def _parse_date(text: str) -> datetime | None:
    """A date written with an English month name (RFC 2822 included); other languages stay in `attribution`."""
    if not text:
        return None
    for pattern in (_MONTH_FIRST_RE, _DAY_FIRST_RE):
        if match := pattern.search(text):
            hour, minute = int(match["hour"] or 0), int(match["minute"] or 0)
            if match["ampm"] and match["ampm"][0].lower() == "p" and hour < 12:
                hour += 12
            elif match["ampm"] and match["ampm"][0].lower() == "a" and hour == 12:
                hour = 0
            try:
                return datetime(
                    int(match["year"]), _MONTHS[match["month"][:3].lower()], int(match["day"]), hour, minute
                )
            except ValueError:
                return None
    return None
