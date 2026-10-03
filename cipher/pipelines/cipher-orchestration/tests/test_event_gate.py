"""The event gate's skip rule (no DB, no model)."""

from cipher.orchestration.extract_events import gate_skip_reason
from cipher.schemas.content.email import EmailCategory, EmailClient

GMAIL = {"email_client": "gmail", "state": None, "labels": ["Inbox", "Category Updates"]}


def test_gmail_labels_map_to_common_categories():
    labels = ["Inbox", "Category Purchases", "Category Updates"]
    assert EmailCategory.for_email(EmailClient.GMAIL, labels) == [EmailCategory.UPDATES, EmailCategory.PURCHASES]
    assert EmailCategory.for_email(EmailClient.OUTLOOK, labels) == []


def test_score_threshold():
    assert gate_skip_reason(0.5, GMAIL, threshold=0.4) is None
    assert gate_skip_reason(0.3, GMAIL, threshold=0.4) == "gate score below 0.40"


def test_client_category_and_state_skip_regardless_of_score():
    promo = GMAIL | {"labels": ["Category Promotions"]}
    assert gate_skip_reason(0.99, promo, threshold=0.4) == "mail category: promotions"
    assert gate_skip_reason(0.99, promo, threshold=0.4, skip_categories=frozenset()) is None
    # the client's verdict is reported ahead of a low score
    assert gate_skip_reason(0.1, GMAIL | {"state": "spam"}, threshold=0.4) == "mail state: spam"
    # stored categories win over labels (parsed after categories were added)
    assert gate_skip_reason(0.99, GMAIL | {"categories": ["promotions"]}, threshold=0.4) == "mail category: promotions"


def test_non_email_text_only_uses_the_score():
    assert gate_skip_reason(0.9, {"title": "report.pdf"}, threshold=0.4) is None
    assert gate_skip_reason(0.9, None, threshold=0.4) is None
