import re
import json
from pathlib import Path

import iso639
from loguru import logger
import pandas as pd
import typer

from nerd.schemas.enums import Mode
from nerd.core.utils import get_sentence_hash


DATASET_NAME = "multinerd"
# from README.md except:
## changing PER to PERSON since ontonotes uses that due to conflict with PERCENT
## changing EVE to EVENT since ontonotes uses that
TAG_MAPPING = {
    "O": 0,
    "B-PERSON": 1,
    "I-PERSON": 2,
    "B-ORG": 3,
    "I-ORG": 4,
    "B-LOC": 5,
    "I-LOC": 6,
    "B-ANIM": 7,
    "I-ANIM": 8,
    "B-BIO": 9,
    "I-BIO": 10,
    "B-CEL": 11,
    "I-CEL": 12,
    "B-DIS": 13,
    "I-DIS": 14,
    "B-EVENT": 15,
    "I-EVENT": 16,
    "B-FOOD": 17,
    "I-FOOD": 18,
    "B-INST": 19,
    "I-INST": 20,
    "B-MEDIA": 21,
    "I-MEDIA": 22,
    "B-MYTH": 23,
    "I-MYTH": 24,
    "B-PLANT": 25,
    "I-PLANT": 26,
    "B-TIME": 27,
    "I-TIME": 28,
    "B-VEHI": 29,
    "I-VEHI": 30
}
TAG_LOOKUP = {v: k for k, v in TAG_MAPPING.items()}


app = typer.Typer()


@app.command()
def download(huggingface_token:str, out_dir: Path):
    """Download the dataset from Hugging Face.
    
    Alternatively, use the huggingface-cli command:
    huggingface-cli download --repo-type dataset Babelscape/multinerd --local-dir
    """
    import huggingface_hub
    from huggingface_hub import hf_hub_download

    huggingface_hub.login(token=huggingface_token)
    # download the dataset
    hf_hub_download(
        repo_id=f"Babelscape/{DATASET_NAME}",
        repo_type="dataset",
        local_dir=out_dir,
        local_dir_use_symlinks=False,
        ignore_patterns=["*.py", "*.sh", "*.md", "README.md"]
    )


def convert_to_parquet(file_path: Path, out_path: Path):
    """Convert a file to parquet."""
    data = []
    with open(file_path, "r") as fb:
        for line in fb:
            sentence = json.loads(line)
            md5 = get_sentence_hash(sentence["tokens"])
            language = iso639.Language.match(sentence["lang"]).part3
            tags = [TAG_LOOKUP[tag] for tag in sentence["ner_tags"]]
            data.append({
                "dataset": DATASET_NAME,
                "doc_id": None,
                "md5": md5,
                "tokens": sentence["tokens"],
                "tags": tags,
                "language": language
            })
    df = pd.DataFrame(data)
    df.to_parquet(out_path, index=False)

    
@app.command()
def format(
    in_dir: Path = typer.Option(
        ...,
        help="Path to the input directory containing train, test, val subdirectories with jsonl files."
    ),
    out_dir: Path = typer.Option(
        ...,
        help="Path to the output directory to create a dataset in NERD format per language."
    )
):
    """Format the dataset to NERD format."""
    for mode in Mode:
        for file_path in (in_dir / mode.value).glob("*.jsonl"):
            filename = file_path.name
            match = re.match(fr"^{mode}\_(\w{{2}})\.jsonl$", filename)
            language = match.group(1)
            language = iso639.Language.match(language).part3  # Convert to ISO 639-3
            # separate by language
            sub_out_dir = f"multinerd-{language}"
            out_path = out_dir / sub_out_dir / f"{mode.value}.parquet"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            # convert to parquet
            convert_to_parquet(file_path=file_path, out_path=out_path)
            logger.info(f"Converted {file_path} to {out_path}")
            

if __name__ == "__main__":
    app()