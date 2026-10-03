"""Multilingual word lists for `extract-signatures`' first pass. Edit this file to add a language.

Two lists, both keyed by ISO 639-1 language code. Order and language keys are only for
humans -- every phrase from every language is checked against every email.

* `FAREWELLS` -- sign-off phrases ("Best regards", "С уважением"). A line that *is* one
  of these (ignoring case and trailing punctuation) marks the end of the message and the
  start of a likely signature. Add the phrase as people write it on its own line; no
  regex, no trailing comma.
* `REPLY_MARKERS` -- how a quoted reply or forward begins ("On … wrote:"). Everything
  from the first marker down is someone else's text and is never read. These are regular
  expressions matched at the start of a line (case-insensitive); keep them anchored on the
  fixed words so they don't swallow body text.

To add a language: add one entry to each dict, then run
`uv run pytest pipelines/cipher-orchestration/tests/test_signature_cues.py`.
"""

FAREWELLS: dict[str, tuple[str, ...]] = {
    "en": (
        "best", "best regards", "best wishes", "kind regards", "regards", "warm regards", "warmest regards",
        "many thanks", "thanks", "thank you", "thanks again", "cheers", "sincerely", "yours sincerely",
        "yours truly", "yours", "all the best", "take care", "respectfully", "with thanks",
    ),
    "de": (
        "mit freundlichen grüßen", "mit freundlichen grüssen", "freundliche grüße", "beste grüße", "viele grüße",
        "liebe grüße", "herzliche grüße", "mit besten grüßen", "gruß", "grüße", "lg", "mfg", "danke",
        "vielen dank",
    ),
    "fr": (
        "cordialement", "bien cordialement", "bien à vous", "salutations", "meilleures salutations",
        "sincères salutations", "amicalement", "bonne journée", "merci", "merci beaucoup",
    ),
    "es": (
        "saludos", "saludos cordiales", "un saludo", "atentamente", "cordialmente", "un abrazo", "gracias",
        "muchas gracias",
    ),
    "it": ("cordiali saluti", "distinti saluti", "saluti", "un saluto", "grazie", "grazie mille"),
    "pt": ("atenciosamente", "cumprimentos", "melhores cumprimentos", "abraços", "obrigado", "obrigada"),
    "nl": ("met vriendelijke groet", "met vriendelijke groeten", "groeten", "hartelijke groet", "bedankt"),
    "ru": ("с уважением", "всего доброго", "всего хорошего", "спасибо", "с наилучшими пожеланиями"),
    "uk": ("з повагою", "дякую", "з найкращими побажаннями"),
    "pl": ("pozdrawiam", "z poważaniem", "serdecznie pozdrawiam", "dziękuję"),
    "tr": ("saygılarımla", "iyi çalışmalar", "teşekkürler", "teşekkür ederim"),
    "ar": ("مع خالص التحية", "مع التحية", "تحياتي", "وتفضلوا بقبول فائق الاحترام", "شكراً", "شكرا", "مع الشكر"),
    "fa": ("با احترام", "با سپاس", "سپاس", "ممنون"),
    "he": ("בברכה", "תודה", "בכבוד רב"),
    "zh": ("此致", "敬礼", "此致敬礼", "祝好", "谢谢", "顺祝商祺", "祝商祺"),
    "ja": ("よろしくお願いいたします", "よろしくお願いします", "宜しくお願い致します", "以上", "敬具"),
    "ko": ("감사합니다", "감사드립니다", "드림", "올림"),
    "hi": ("धन्यवाद", "सादर", "शुभकामनाओं सहित"),
    "vi": ("trân trọng", "thân mến", "cảm ơn"),
    "id": ("salam", "hormat saya", "terima kasih"),
}  # fmt: skip

REPLY_MARKERS: dict[str, tuple[str, ...]] = {
    "en": (r"On .{0,200}wrote:\s*$", r"-{2,}\s*Original Message", r"-{2,}\s*Forwarded message", r"From:\s", r"Sent from my "),
    "de": (r"Am .{0,200}schrieb.{0,80}:\s*$", r"-{2,}\s*Ursprüngliche Nachricht", r"Von:\s", r"Gesendet von meinem "),
    "fr": (r"Le .{0,200}a écrit\s*:\s*$", r"-{2,}\s*Message d'origine", r"De\s*:\s", r"Envoyé de mon "),
    "es": (r"El .{0,200}escribió:\s*$", r"-{2,}\s*Mensaje original", r"De:\s", r"Enviado desde mi "),
    "it": (r"Il .{0,200}ha scritto:\s*$", r"-{2,}\s*Messaggio originale", r"Da:\s"),
    "pt": (r"Em .{0,200}escreveu:\s*$", r"-{2,}\s*Mensagem original", r"De:\s"),
    "nl": (r"Op .{0,200}schreef.{0,80}:\s*$", r"-{2,}\s*Oorspronkelijk bericht", r"Van:\s"),
    "ru": (r".{0,200}написал\(?а?\)?:\s*$", r"-{2,}\s*Исходное сообщение", r"От:\s"),
    "zh": (r"-{2,}\s*原始邮件", r"发件人[:：]"),
    "ja": (r"-{2,}\s*元のメッセージ", r"差出人[:：]"),
    "ar": (r"من\s*:\s",),
    "any": (r">",),  # a quoted line
}  # fmt: skip
