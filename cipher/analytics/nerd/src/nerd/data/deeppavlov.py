from enum import StrEnum
import re
import hashlib
import json
from pathlib import Path
import subprocess

import iso639
from loguru import logger
import pandas as pd
import typer

from nerd.core.utils import is_punctuation
from nerd.schemas.enums import Mode


app = typer.Typer()

BASE_URL = "http://files.deeppavlov.ai/deeppavlov_data"

class Dataset(StrEnum):
    """Enum for DeepPavlov datasets."""
    CONLL03 = "conll03"
    ONTONOTES = "ontonotes"


LINK = {
    Dataset.CONLL03: f"{BASE_URL}/conll2003_v2.tar.gz",
    Dataset.ONTONOTES: f"{BASE_URL}/ontonotes_ner.tar.gz"
}



@app.command()
def download(dataset: Dataset, out_dir: Path):
    """Download a dataset from DeepPavlov since all structured
    the same.
    
    Alternatively, download manually:
    
    wget http://files.deeppavlov.ai/deeppavlov_data/conll2003_v2.tar.gz
    tar -xzvf "conll2003_v2.tar.gz"
    """
    url = LINK[dataset]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_dir = out_dir / dataset
    dataset_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["wget", url, "-O", out_dir / f"{dataset}.tar.gz"])
    subprocess.run(["tar", "-xzvf", out_dir / f"{dataset}.tar.gz", "-C", dataset_dir])
    subprocess.run(["rm", out_dir / f"{dataset}.tar.gz"])


def format_file(file_path: Path, out_dir: Path):
    """Format a file into a Parquet file NERD dataset."""
    raise NotImplementedError("Not implemented yet. They seem to only have the English version")

    # mode = file_path.stem
    # mode = Mode.VAL if mode == "valid" else mode
    # if mode not in Mode:
    #     raise ValueError(f"Unknown mode: {mode}")
    # out_path = out_dir / f"{mode}.parquet"

    # out_dir.mkdir(parents=True, exist_ok=True)
    # df = pd.read_csv(file_path, sep="\t", encoding="utf-8")
    # df = df.rename(columns={"index": "doc_id", "sentence": "text", "tag": "tags"})
    # df["md5"] = df["doc_id"].apply(lambda x: hashlib.md5(x.encode()).hexdigest())
    # df["lang"] = iso639.to_iso639_3("en")
    # df.to_parquet(out_dir / f"{file_path.stem}.parquet")

if __name__ == "__main__":
    app()
