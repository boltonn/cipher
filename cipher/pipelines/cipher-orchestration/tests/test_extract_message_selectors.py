"""Import + shape checks for the Message -> selector producer (DB path is integration-only)."""

from cipher.orchestration.extract_message_selectors import _EXTRACTOR, extract_message_selectors_workflow


def test_workflow_is_importable_and_named():
    """The producer exists and tags its mentions distinctly for the re-run guard."""
    assert callable(extract_message_selectors_workflow)
    assert _EXTRACTOR == "messages"
