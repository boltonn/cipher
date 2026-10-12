from cipher.utils.uri import read_bytes


def download_uri(uri: str) -> bytes:
    """Download the content from the given URI."""
    return read_bytes(uri)
