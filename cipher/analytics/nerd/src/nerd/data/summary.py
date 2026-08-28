from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from rich.pretty import pprint
import polars as pl
import typer

from nerd.core.utils import display_dataframe
from nerd.schemas.enums import Mode

app = typer.Typer()

def get_size(file_path: Path) -> str:
    size = file_path.stat().st_size
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 ** 3:
        return f"{size / 1024 ** 2:.2f} MB"
    else:
        return f"{size / 1024 ** 3:.2f} GB"


@dataclass
class FileSummary:
    size: str
    n_docs: int
    n_sentences: int
    n_tokens: int
    n_entities: int
    labels: dict[str, int]


def _summarize_file(file_path: Path, chunk_size: Optional[int] = 10_000) -> FileSummary:
    """Summarize a NERD dataset file (even if it doesnt fit in memory)."""
    size = get_size(file_path)
    df = pl.scan_parquet(file_path)

    stats = (
        df.select([
            pl.col("doc_id").drop_nulls().n_unique().alias("n_docs"),
            pl.col("md5").drop_nulls().n_unique().alias("n_sentences"),
        ])
        .collect()
    )
    # turn to dict
    n_docs = stats["n_docs"][0]
    n_sentences = stats["n_sentences"][0]

    n_tokens = 0
    label_counts = defaultdict(int) # based off tokens starting with B

    # 'tags' column ex: [O, O, O, O, O, O, O, B-LOC, O, O, O, O, O, O,... 
    
    reader = pl.read_parquet(file_path, n_rows=chunk_size)
    for frame in reader.iter_slices(n_rows=chunk_size):
        for row in frame.iter_rows(named=True):
            tags = row["tags"]
            n_tokens += len(tags)

            
            # Update entity types counter
            for tag in tags:
                if tag.startswith('B-'):
                    entity_type = tag[2:]  # Remove B- or I- prefix
                    label_counts[entity_type] += 1

    n_entities = sum(label_counts.values())
    return FileSummary(
        size=size,
        n_docs=n_docs,
        n_sentences=n_sentences,
        n_tokens=n_tokens,
        n_entities=n_entities,
        labels=dict(label_counts),
    )

@app.command()
def summarize_file(path: Path, n: Optional[int] = 10):
    """Summarize a NERD dataset file."""
    summary = _summarize_file(path)
    pprint(asdict(summary), expand_all=True)
    display_dataframe(pl.read_parquet(path, n_rows=n), title="Sample of the dataset", n_rows=n)

def summarize_dataset(path: Path):
    """Summarize a NERD dataset directory."""
    files = list(path.glob("*.parquet"))
    summaries = [summarize_file(f) for f in files]
    return summaries

@app.command()
def summary(path: Path, nrows: Optional[int] = 10, mode: Optional[Mode] = None):
    """Get the summary of a NERD dataset. ie. the number of rows in each file
    and the breakdown of the labels. The summary should be a table of counts
    for each label in each file and the total number of rows in each file by mode.
    
    Args:
        path (Path): Path to a NERD dataset or NERD dataset file.
        nrows (int): The number of rows to display. Defaults to 10.
        mode (Mode, optional): The mode of the dataset. If not provided,it will get the counts for all modes.
    """
    if path.is_dir():
        files = list(path.glob("**/*.parquet"))
    else:
        files = [path]

    if mode is not None:
        # train.parquet, dev.parquet, test.parquet
        files = [f for f in files if f.stem == mode.value.lower()]
        
    summaries = [summarize_file(f) for f in files]
    # Print out a block about the meta and then a DataFrame of counts similar
    
    
if __name__ == "__main__":
    app()