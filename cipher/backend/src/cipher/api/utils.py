from pathlib import Path


def download_uri(uri: str) -> bytes:
    """Download the content from the given URI."""
    if uri.startswith("file://"):
        file_path = uri[7:]  # Remove 'file://' prefix
        with open(file_path, "rb") as f:
            return f.read()
    elif uri.startswith("s3://"):
        raise NotImplementedError("S3 URI download not implemented yet.")
    elif Path(uri).exists():
        with open(uri, "rb") as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported URI scheme in {uri}")
