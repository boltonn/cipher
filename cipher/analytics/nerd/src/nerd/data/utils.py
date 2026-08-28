import hashlib

from nerd.core.utils import is_punctuation


def get_sentence_hash(tokens: list[str]) -> str:
    """Get a hash of the sentence.
    Delimiter is space unless the token is punctuation.
    """
    sentence = ""
    for token in tokens:
        if len(token)==1 and is_punctuation(token):
            sentence += token
        else:
            sentence += " " + token
    return hashlib.md5(sentence.encode()).hexdigest()