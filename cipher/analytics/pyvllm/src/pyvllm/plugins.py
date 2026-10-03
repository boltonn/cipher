"""vLLM general plugin: make `vllm serve jinaai/jina-ocr-v1` work like any other model.

jina-ocr-v1 ships its vLLM support as a module inside the model snapshot
(`deepseek_ocr_mtp.py`) that must register its architectures before the engine
starts. vLLM calls this in the server and in every worker process.
"""

import sys

JINA_OCR_REPO = "jinaai/jina-ocr-v1"


def register_jina_ocr() -> None:
    """Register jina-ocr-v1's architectures when its snapshot is on disk; a no-op otherwise."""
    from huggingface_hub import snapshot_download

    try:
        snapshot = snapshot_download(JINA_OCR_REPO, local_files_only=True)
    except Exception:
        return
    if snapshot not in sys.path:
        sys.path.insert(0, snapshot)
    import deepseek_ocr_mtp

    deepseek_ocr_mtp.register()
