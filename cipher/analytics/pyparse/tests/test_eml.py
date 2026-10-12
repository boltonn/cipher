import base64
import struct
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
from pyparse.children import describe_only
from pyparse.parsers.email import EmailOptions, parse_eml
from pyparse.parsers.email.rtf import rtf_to_text
from pyparse.parsers.email.smime import signed_content


def _forward_as_attachment() -> bytes:
    inner = EmailMessage()
    inner["From"], inner["To"], inner["Subject"] = "Alice <alice@x.com>", "bob@y.com", "Contract"
    inner.set_content("Inner body from Alice")
    inner.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf", filename="contract.pdf")
    outer = EmailMessage()
    outer["From"], outer["To"], outer["Subject"] = "Bob <bob@y.com>", "carol@z.com", "Fwd: Contract"
    outer.set_content("See attached")
    outer.add_attachment(inner)
    return outer.as_bytes()


def test_attached_email_is_a_child_file_not_merged_text():
    """A forwarded-as-attachment email keeps its own body and attachments; the outer email gets one .eml child."""
    email = parse_eml(_forward_as_attachment())
    assert "Inner body" not in (email.plain or "")
    [attached] = email.attachments
    assert attached.filename == "Contract.eml" and attached.filetype_group == "email"


def test_cid_images_are_inline_not_attachments():
    """Images the HTML shows through cid: links are not attachments, and can be embedded in the HTML."""
    message = EmailMessage()
    message["From"], message["Subject"] = "a@x.com", "Logo"
    message.set_content("hi")
    message.add_alternative('<p>hi</p><img src="cid:logo.png@01D5">', subtype="html")
    message.get_payload()[1].add_related(
        b"\x89PNG logo",
        maintype="image",
        subtype="png",
        cid="<logo.png@01D5>",
        disposition="inline",
        filename="logo.png",
    )
    message.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf", filename="report.pdf")
    stored: list[str] = []

    def sink(*, data: bytes, filename: str | None):
        stored.append(filename or "")
        return describe_only(data=data, filename=filename)

    email = parse_eml(message.as_bytes(), sink=sink)
    assert [child.filename for child in email.attachments] == ["report.pdf"] and sorted(stored) == [
        "logo.png",
        "report.pdf",
    ]
    assert "cid:logo.png@01D5" in (email.html or "")

    stored.clear()
    parse_eml(message.as_bytes(), sink=sink, options=EmailOptions(save_inline_images=False))
    assert stored == ["report.pdf"]

    embedded = parse_eml(message.as_bytes(), options=EmailOptions(embed_inline_images=True))
    assert "cid:" not in (embedded.html or "")
    assert f"base64,{base64.b64encode(b'\x89PNG logo').decode()}" in (embedded.html or "")


def test_thread_headers_and_conversation_root():
    """Without a client thread id, the conversation is the thread's root Message-ID."""
    raw = (
        b"From: a@x.com\r\nSubject: Re: hi\r\nMessage-ID: <c@x>\r\nIn-Reply-To: <b@x>\r\n"
        b"References: <a@x>\r\n <b@x>\r\n\r\nbody\r\n"
    )
    metadata = parse_eml(raw).metadata
    assert (metadata.references, metadata.in_reply_to, metadata.conversation_id) == (["a@x", "b@x"], "b@x", "a@x")
    assert parse_eml(b"From: a@x.com\r\nMessage-ID: <a@x>\r\n\r\nbody\r\n").metadata.conversation_id == "a@x"


def test_outlook_thread_index_keeps_only_the_thread_root():
    """Every reply appends 5 bytes to Thread-Index; replies in one thread share its first 22."""
    root = bytes(range(22))
    first, reply = base64.b64encode(root).decode(), base64.b64encode(root + b"\x01\x02\x03\x04\x05").decode()
    ids = {
        parse_eml(f"From: a@x.com\r\nThread-Index: {index}\r\n\r\nbody\r\n".encode()).metadata.conversation_id
        for index in (first, reply)
    }
    assert ids == {first}


def _signed_p7m(inner: bytes) -> bytes:
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import pkcs7
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Alice")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    builder = pkcs7.PKCS7SignatureBuilder().set_data(inner).add_signer(cert, key, hashes.SHA256())
    return builder.sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])


def test_opaque_signed_smime_is_read_as_the_email_itself():
    """A signed `smime.p7m` wraps the real body and attachments; they are this email's own."""
    inner = EmailMessage()
    inner.set_content("Signed body from Alice")
    inner.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf", filename="contract.pdf")
    outer = EmailMessage()
    outer["From"], outer["Subject"] = "Alice <alice@x.com>", "Signed"
    outer.set_content(
        _signed_p7m(inner.as_bytes()),
        maintype="application",
        subtype="pkcs7-mime",
        filename="smime.p7m",
        params={"smime-type": "signed-data"},
    )
    email = parse_eml(outer.as_bytes())
    assert "Signed body from Alice" in email.plain
    assert [attachment.filename for attachment in email.attachments] == ["contract.pdf"]


def test_ber_indefinite_length_signed_data():
    """Outlook writes BER: indefinite lengths and a chunked octet string."""
    content = b"Content-Type: text/plain\r\n\r\nhello"
    chunks = b"".join(b"\x04" + bytes([len(piece)]) + piece for piece in (content[:10], content[10:]))
    octets = b"\x24\x80" + chunks + b"\x00\x00"
    encapsulated = b"\x30\x80\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x07\x01\xa0\x80" + octets + b"\x00\x00\x00\x00"
    signed_data = b"\x30\x80\x02\x01\x01\x31\x00" + encapsulated + b"\x31\x00\x00\x00"
    p7m = b"\x30\x80\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x07\x02\xa0\x80" + signed_data + b"\x00\x00\x00\x00"
    assert signed_content(p7m) == content
    assert signed_content(b"\x30\x03\x02\x01\x01") is None


def _winmail(*attributes: tuple[int, int, bytes]) -> bytes:
    out = struct.pack("<IH", 0x223E9F78, 0)
    for level, attribute, data in attributes:
        out += struct.pack("<BII", level, attribute, len(data)) + data + struct.pack("<H", sum(data) & 0xFFFF)
    return out


def _mapi_unicode(property_id: int, value: str) -> bytes:
    raw = value.encode("utf-16-le") + b"\x00\x00"
    return struct.pack("<HHII", 0x001F, property_id, 1, len(raw)) + raw + b"\x00" * (-len(raw) % 4)


def test_winmail_dat_is_unpacked_into_its_files_and_body():
    """Outlook hides the real attachments (and here the only body) inside winmail.dat."""
    body = _mapi_unicode(0x1000, "Body only in TNEF")
    attachment_props = _mapi_unicode(0x3707, "Quarterly report.xlsx")
    winmail = _winmail(
        (1, 0x00069003, struct.pack("<I", 1) + body),
        (2, 0x00069002, b"\x00" * 14),
        (2, 0x00018010, b"QUARTE~1.XLS\x00"),
        (2, 0x0006800F, b"PK\x03\x04 spreadsheet bytes"),
        (2, 0x00069005, struct.pack("<I", 1) + attachment_props),
    )
    outer = EmailMessage()
    outer["From"] = "Bob <bob@y.com>"
    outer.add_attachment(winmail, maintype="application", subtype="ms-tnef", filename="winmail.dat")
    email = parse_eml(outer.as_bytes())
    assert email.plain == "Body only in TNEF"
    assert [attachment.filename for attachment in email.attachments] == ["Quarterly report.xlsx"]


def test_digest_items_are_attached_emails():
    """multipart/digest parts default to message/rfc822 even without a Content-Type."""
    raw = (
        b"From: list@x.com\r\nSubject: Digest\r\nMIME-Version: 1.0\r\n"
        b'Content-Type: multipart/digest; boundary="b"\r\n\r\n'
        b"--b\r\n\r\nFrom: a@x.com\r\nSubject: First\r\n\r\none\r\n"
        b"--b\r\n\r\nFrom: c@x.com\r\nSubject: Second\r\n\r\ntwo\r\n--b--\r\n"
    )
    assert [attachment.filename for attachment in parse_eml(raw).attachments] == ["First.eml", "Second.eml"]


def test_rtf_body_wrapping_html_is_unwrapped():
    r"""Outlook's RTF bodies usually wrap HTML (`\fromhtml1`); the HTML comes back, RTF-only markup doesn't."""
    rtf = (
        rb"{\rtf1\ansi\ansicpg1252\fromhtml1 {\fonttbl{\f0 Arial;}}"
        rb"{\*\htmltag19 <html>}{\*\htmltag64 <p>}\htmlrtf {\htmlrtf0 Caf\'e9 with Megan\htmlrtf }\htmlrtf0"
        rb"{\*\htmltag72 </p>}{\*\htmltag27 </html>}}"
    )
    assert rtf_to_text(rtf) == "<html><p>Café with Megan</p></html>"


def test_plain_rtf_body_is_read_as_text():
    """Control words, font tables and unicode escapes resolve to plain text with line breaks."""
    rtf = rb"{\rtf1\ansi{\fonttbl{\f0 Calibri;}}\f0 Hello Nick,\par See you \u8212? soon.\par}"
    assert rtf_to_text(rtf) == "Hello Nick,\nSee you — soon.\n"


def test_inbox_and_sent_copies_share_a_meaningful_hash_without_message_id():
    """Without a Message-ID, copies match on sender, To/Cc, date, subject and text -- not Bcc, links or tags."""
    sent = (
        b"From: Megan <megan@x.com>\r\nTo: nick@y.com, ed@z.com\r\nBcc: boss@x.com\r\n"
        b"Date: Mon, 21 Jul 2025 07:28:00 -0400\r\nSubject: Lease\r\n\r\n"
        b"Can we meet Tuesday? https://x.com/lease\r\n"
    )
    inbox = (
        b"Received: from mx.y.com\r\nDelivered-To: nick@y.com\r\nFrom: megan@x.com\r\nTo: ED@z.com, nick@y.com\r\n"
        b"Date: Mon, 21 Jul 2025 11:28:00 +0000\r\nSubject: [EXTERNAL] Lease\r\n\r\n"
        b"Can we meet  Tuesday?\r\nhttps://safelinks.example/?url=x.com%2Flease\r\n"
    )
    reply = inbox.replace(b"Subject: [EXTERNAL] Lease", b"Subject: RE: Lease")
    sent_meta, inbox_meta, reply_meta = (parse_eml(raw).metadata for raw in (sent, inbox, reply))
    assert sent_meta.meaningful_hash == inbox_meta.meaningful_hash != reply_meta.meaningful_hash
    assert sent_meta.meaningful_hash_source == "content"
    with_id = parse_eml(b"From: a@x.com\r\nMessage-ID: <abc@x>\r\n\r\nbody\r\n").metadata
    assert with_id.meaningful_hash_source == "message_id"
