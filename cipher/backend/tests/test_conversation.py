from datetime import UTC, datetime

from cipher.api.routes.files import link_conversation
from cipher.schemas.content.email import ConversationEmail

FORWARD = "nick do u know what happened? E F Bolton CPCU"
REPLY = (
    "yah i dared them that they wouldnt steal something from wawa so they did.\n\n"
    "--- On Mon, 5/3/10, E F bolton CPCU <efbolton@yahoo.com> wrote:\n\n"
    f"{FORWARD}\n"
)
REPLY_TO_REPLY = (
    "Cool thxs do u think we need to have mom attend?\n\n"
    "From: Nick Bolton [mailto:bolton213@yahoo.com]\nSent: Tuesday, May 04, 2010 2:10 PM\n"
    "Subject: Re: Fw: PARENT MEETING\n\n"
    "yah i dared them that they wouldnt steal something from wawa so they did.\n"
)
UNRELATED = "Totally different topic about the parent meeting snacks rota for next season."


def _email(file_id: str, title: str, day: int, sender: str) -> ConversationEmail:
    return ConversationEmail(
        file_id=file_id, title=title, from_address=sender, date_sent=datetime(2010, 5, day, tzinfo=UTC)
    )


def test_quoted_text_links_a_chain_the_headers_split():
    """The forward + reply (one header conversation) pull in the reply-to-reply that quotes them, not the bystander."""
    members = [
        (_email("forward", "Fw: PARENT MEETING", 3, "efbolton@yahoo.com"), FORWARD),
        (_email("reply", "Re: Fw: PARENT MEETING", 4, "bolton213@yahoo.com"), REPLY),
    ]
    candidates = [
        (_email("reply-2", "RE: Fw: PARENT MEETING", 5, "efbolton@williamsagency.com"), REPLY_TO_REPLY),
        (_email("bystander", "Re: Parent meeting", 6, "efbolton@yahoo.com"), UNRELATED),
    ]
    emails, is_linked = link_conversation(members=members, candidates=candidates, title="Re: Fw: PARENT MEETING")
    assert [email.file_id for email in emails] == ["forward", "reply", "reply-2"]
    assert is_linked
    assert emails[1].preview.startswith("yah i dared them") and "wrote" not in emails[1].preview


def test_same_subject_without_quotes_stays_apart():
    """Two "Weekly report" emails share a subject but neither quotes the other: no link."""
    members = [(_email("week-1", "Re: Weekly report", 3, "a@x.com"), "Numbers for week one are attached.")]
    candidates = [(_email("week-2", "Re: Weekly report", 10, "a@x.com"), "Numbers for week two are attached.")]
    emails, is_linked = link_conversation(members=members, candidates=candidates, title="Re: Weekly report")
    assert [email.file_id for email in emails] == ["week-1"]
    assert not is_linked
