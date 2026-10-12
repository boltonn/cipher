import io
import struct

from pyparse.parsers.email import parse_eml
from pyparse.parsers.email.msg_embedded import EMBEDDED_MESSAGE_STORAGE, embedded_message_eml

ATTACH = "__attach_version1.0_#00000000"


class FakeOle:
    """The slice of `OleFileIO` the rebuild reads, backed by a dict of stream paths."""

    def __init__(self, streams: dict[tuple[str, ...], bytes]) -> None:
        self.streams = streams
        self.storages = {path[:depth] for path in streams for depth in range(1, len(path))}

    def exists(self, path: list[str]) -> bool:
        return tuple(path) in self.streams or tuple(path) in self.storages

    def openstream(self, path: list[str]) -> io.BytesIO:
        return io.BytesIO(self.streams[tuple(path)])

    def listdir(self, streams: bool, storages: bool) -> list[list[str]]:
        return [list(path) for path in self.storages] if storages else [list(path) for path in self.streams]


def _unicode(value: str) -> bytes:
    return value.encode("utf-16-le")


def test_attached_outlook_item_is_rebuilt_as_an_eml_with_its_own_attachment():
    """Without transport headers, sender, recipients, date and attachments come from MAPI properties."""
    message = (ATTACH, EMBEDDED_MESSAGE_STORAGE)
    recipient = (*message, "__recip_version1.0_#00000000")
    attachment = (*message, "__attach_version1.0_#00000000")
    submit_time = struct.pack("<IIQ", 0x0039 << 16 | 0x0040, 0, 133_000_000_000_000_000)
    cc_type = struct.pack("<IIQ", 0x0C15 << 16 | 0x0003, 0, 2)
    ole = FakeOle(
        {
            (*message, "__substg1.0_0037001F"): _unicode("Lease renewal"),
            (*message, "__substg1.0_1000001F"): _unicode("Please sign by Friday"),
            (*message, "__substg1.0_0C1A001F"): _unicode("Megan Flick"),
            (*message, "__substg1.0_5D01001F"): _unicode("megan@x.com"),
            (*message, "__properties_version1.0"): b"\x00" * 24 + submit_time,
            (*recipient, "__substg1.0_3001001F"): _unicode("Nick"),
            (*recipient, "__substg1.0_39FE001F"): _unicode("nick@y.com"),
            (*recipient, "__properties_version1.0"): b"\x00" * 8 + cc_type,
            (*attachment, "__substg1.0_3707001F"): _unicode("lease.pdf"),
            (*attachment, "__substg1.0_37010102"): b"%PDF-1.4 lease",
        }
    )
    email = parse_eml(embedded_message_eml(ole, ATTACH))
    metadata = email.metadata
    assert (metadata.title, metadata.sent_from.name, metadata.sent_from.value) == (
        "Lease renewal",
        "Megan Flick",
        "megan@x.com",
    )
    assert [cc.value for cc in metadata.cc] == ["nick@y.com"]
    assert metadata.date_sent.year == 2022
    assert email.plain.strip() == "Please sign by Friday"
    assert [attachment.filename for attachment in email.attachments] == ["lease.pdf"]
