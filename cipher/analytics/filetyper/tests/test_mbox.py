from filetyper.models.magic import MagicNumberFilterTyper


def test_mbox_is_told_apart_from_a_single_email_without_its_extension():
    """Thunderbird keeps folders as extensionless mbox files (`Inbox`); an .eml never opens with a From_ line."""
    typer = MagicNumberFilterTyper()
    assert typer.infer_bytes(b"From - Sat Jan  3 12:00:00 2015\nFrom: a@x.com\n\nhi\n")["filetype"] == "mbox"
    assert typer.infer_bytes(b"From 1706643591@xxx Thu Jul 29 18:09:20 +0000 2021\r\n")["filetype"] == "mbox"
    assert typer.infer_bytes(b"From: a@x.com\nSubject: hi\n\nbody\n") is None
    assert typer.infer_bytes(b"From the desk of the editor\n") is None
