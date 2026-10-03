from pyprompt.offsets import find_span


def test_exact_then_case_insensitive():
    """Verbatim text is found as is, then ignoring case."""
    text = "Welcome to Gold's Gym Tysons!"
    assert text[slice(*find_span(text, "Gold's Gym Tysons"))] == "Gold's Gym Tysons"
    assert text[slice(*find_span(text, "gold's gym tysons"))] == "Gold's Gym Tysons"


def test_inflected_word_endings_match_and_return_the_source_form():
    """The model's dictionary form finds the inflected text, returned as the email writes it."""
    text = "Ваше членство в яхт-клубе «Нева» продлено."
    assert text[slice(*find_span(text, "яхт-клуб «Нева»"))] == "яхт-клубе «Нева»"
    german = "Beitrag des Sportvereins Hamburg erhalten."
    assert german[slice(*find_span(german, "Sportverein Hamburg"))] == "Sportvereins Hamburg"


def test_different_words_do_not_match():
    """Only endings may differ: a different word, or a short stem, is no match."""
    assert find_span("Welcome to the Rotary Club", "Lions Club") is None
    assert find_span("at the gym", "gem") is None
