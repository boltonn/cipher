from enum import StrEnum
import re
import hashlib
from pathlib import Path

import iso639
from loguru import logger
import pandas as pd
import typer


app = typer.Typer()

BASE_URL = "https://raw.githubusercontent.com/UniversalNER"
# NOTE: Not comprehensive list; just a subset of languages
REGISTRY = {
    "UNER_Russian-PUD": [
        "ru_pud-ud-test.iob2"
    ],
    "UNER_Portuguese-PUD": [
        "pt_pud-ud-test.iob2"
    ],
    "UNER_German-PUD": [
        "de_pud-ud-test.iob2"
    ],
    "UNER_English-PUD": [
        "en_pud-ud-test.iob2"
    ],
    "UNER_English-EWT": [
        "en_ewt-ud-dev.iob2",
        "en_ewt-ud-test.iob2",
        "en_ewt-ud-train.iob2"
    ],
    "UNER_Chinese-PUD": [
        "zh_pud-ud-test.iob2"
    ],
    "UNER_Chinese-GSDSIMP": [
        "zh_gsdsimp-ud-test.iob2",
        "zh_gsdsimp-ud-train.iob2",
        "zh_gsdsimp-ud-dev.iob2"
    ],
    "UNER_Chinese-GSD": [
        "zh_gsd-ud-test.iob2",
        "zh_gsd-ud-train.iob2",
        "zh_gsd-ud-dev.iob2"
    ],
    "UNER_Slovak-SNK": [
        "sk_snk-ud-test.iob2",
        "sk_snk-ud-train.iob2",
        "sk_snk-ud-dev.iob2"
    ],
    "UNER_Serbian-SET": [
        "sr_set-ud-test.iob2",
        "sr_set-ud-train.iob2",
        "sr_set-ud-dev.iob2"
    ],
}

ISO_MAP = {
    "Russian": "rus",
    "Portuguese": "por",
    "German": "deu",
    "English": "eng",
    "Chinese": "zho",
    "Slovak": "slk",
    "Serbian": "srp"
}

def get_language(dataset: str):
    """
    Get the language from the dataset name.
    Args:
        dataset (str): The name of the dataset.
    Returns:
        str: The language of the dataset.
    """
    # Example dataset name: "UNER_Russian-PUD"
    match = re.match(r"UNER_(\w+)-", dataset)
    if match:
        language = match.group(1)
    else:
        raise ValueError(f"Dataset {dataset} does not match expected format.")
    
    return ISO_MAP[language]
    

class UNERDataset(StrEnum):
    """Enum for UNER datasets."""
    RUSSIAN_PUD = "UNER_Russian-PUD"
    PORTUGUESE_PUD = "UNER_Portuguese-PUD"
    GERMAN_PUD = "UNER_German-PUD"
    ENGLISH_PUD = "UNER_English-PUD"
    ENGLISH_EWT = "UNER_English-EWT"
    CHINESE_PUD = "UNER_Chinese-PUD"
    CHINESE_GSDSIMP = "UNER_Chinese-GSDSIMP"
    CHINESE_GSD = "UNER_Chinese-GSD"
    SLOVAK_SNK = "UNER_Slovak-SNK"
    SERBIAN_SET = "UNER_Serbian-SET"
    ALL = "all"


def map_tag(tag: str):
    """Replace PER with PERSON in the tag."""
    tag = tag.strip()
    if tag == "O":
        return "O"
    else:
        # Replace PER with PERSON in the tag
        prefix, entity_type = tag.split("-")
        entity_type = "PERSON" if entity_type == "PER" else entity_type
        return f"{prefix}-{entity_type}"


def get_dataset_files(dataset:str, out_dir: Path):
    """
    Get the dataset files for a given dataset from the UNER registry.
    This function will download the files from the specified GitHub repository
    and save them to the specified output directory.
    Args:
        dataset (str): The name of the dataset to download (e.g., "UNER_Russian-PUD").
        out_dir (Path): The output directory where the files will be saved.
    Returns:
        List[Path]: A list of paths to the downloaded files.
    """
    import os
    
    if dataset not in REGISTRY:
        raise ValueError(f"Dataset {dataset} not found in the UNER registry.")
    
    files_to_download = REGISTRY[dataset]
    downloaded_files = []
    
    branch = "main" if dataset == "UNER_Serbian-SET" else "master"  # Adjust branch if necessary
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for file_name in files_to_download:

        url = f"{BASE_URL}/{dataset}/{branch}/{file_name}"
        response = os.system(f'curl -L -o "{str(out_dir / file_name)}" "{url}"')
        
        if response == 0:
            # If the download was successful, add the file path to the list
            downloaded_files.append(out_dir / file_name)
            logger.info(f"Downloaded {file_name} to {out_dir}")
        else:
            raise RuntimeError(f"Failed to download {file_name} from {url}. Please check the URL or your internet connection.")
        
    return downloaded_files


def convert_iob2_to_parquet(input_file: Path, out_dir: Path):
    """
    Convert UNER IOB file to parquet format with the specified columns:
    dataset, doc_id, md5, tokens, tags
    
    Args:
        input_file (str): Path to the input IOB file
        out_dir (str): Path to the output directory (processed)
    """
    # Initialize lists to store data
    dataset_name = input_file.parent.name  # Extract dataset name from output file path
    logger.info(f"Converting {input_file} to Parquet format for dataset: {dataset_name}")
    language, mode = get_info(input_file.name)  # Extract language and mode from filename
    logger.info(f"Language: {language}, Mode: {mode}")

    data = []
    
    # Initialize variables to track current document and sentence
    doc_id = -1
    sent_id = 0
    text = None #leaving alone sine not always clear how tokenized
    tokens = []
    tags = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            if line.startswith("# newdoc id ="):
                # New document, process previous sentence if exists
                if tokens:
                    md5 = hashlib.md5(text.encode()).hexdigest()
                    data.append({
                        "dataset": dataset_name,
                        "doc_id": doc_id,
                        "md5": md5,
                        "tokens": tokens,
                        "tags": tags,
                        "language": language
                    })
                
                # Reset and set new doc id
                doc_id += 1 
                sent_id = 0 
                tokens = []
                tags = []
                text = None
            
            elif line.startswith("# sent_id ="):
                # New sentence, process previous sentence if exists
                if sent_id and tokens:
                    md5 = hashlib.md5(text.encode()).hexdigest()
                    data.append({
                        "dataset": dataset_name,
                        "doc_id": doc_id,
                        "md5": md5,
                        "tokens": tokens,
                        "tags": tags,
                        "language": language
                    })
                
                # Reset for new sentence
                sent_id += 1
                tokens = []
                tags = []
                text = None
            
            elif line.startswith("# text ="):
                # Store the full text of the sentence
                text = line.replace("# text =", "").strip()
            
            elif re.match(r'^\d+\t', line):  # Line starts with digit followed by tab
                # Token line
                parts = line.split('\t')
                if len(parts) >= 3:
                    token = parts[1]
                    tag = map_tag(parts[2])  # Map tag to standard format
                    tokens.append(token)
                    tags.append(tag)
    
    # Process last sentence if exists
    if sent_id and tokens:
        text = text if text else " ".join(tokens)
        md5 = hashlib.md5(text.encode()).hexdigest()
        data.append({
            "dataset": dataset_name,
            "doc_id": doc_id,
            "md5": md5,
            "tokens": tokens,
            "tags": tags,
            "language": language
        })
    
    # Create DataFrame and save as Parquet
    df = pd.DataFrame(data)

    out_dir.mkdir(parents=True, exist_ok=True)
    output_file = out_dir / f"{mode}.parquet"
    df.to_parquet(output_file, index=False)
    
    return df  # Return the DataFrame for inspection


def get_info(filename: str):
    """
    Extracts the language and mode (train, val, test) from the filename.
    This function assumes the filename format is consistent with the UNER naming convention.
    Args:
        filename (str): The name of the file to extract information from.
    Returns:
        tuple: A tuple containing the language and mode (train, val, test).
    """
    # Example filename: "en_ewt-ud-test.iob2"
    match = re.match(r"^(\w+)_\w+-ud-(train|dev|test)\.iob2$", filename)
    if match:
        language = match.group(1)
        language = iso639.Language.match(language).part3  # Convert to ISO 639-3
        mode = match.group(2)
        # Map 'dev' to 'val' for consistency
        if mode == "dev":
            mode = "val"
        return language, mode
    else:
        raise ValueError(f"Filename {filename} does not match expected format.")


@app.command()
def download(dataset: UNERDataset, out_dir: Path):
    """
    Download the specified dataset from the UNER registry.
    
    Args:
        dataset (str): The name of the dataset to download.
        out_dir (Path): The output directory where the files will be saved.
    """
    if dataset == UNERDataset.ALL:
        for dataset_name in REGISTRY.keys():
            logger.info(f"Downloading dataset: {dataset_name}")
            get_dataset_files(dataset=dataset_name, out_dir=out_dir)
    else:
        logger.info(f"Downloading dataset: {dataset}")
        get_dataset_files(dataset=dataset, out_dir=out_dir)


@app.command()
def format(in_dir: Path, out_dir: Path):
    """
    Convert the IOB2 files in the specified input directory to Parquet format.
    
    Args:
        in_dir (Path): The input directory containing IOB files. (could be dataset level or not)
        out_dir (Path): The output directory where the Parquet files will be saved.
    """
    in_dir = Path(in_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for file in in_dir.glob("**/*.iob2"):
        convert_iob2_to_parquet(file, out_dir)


@app.command()
def main(
    dataset: UNERDataset = typer.Argument(
        UNERDataset.ALL,
        help="The name of the dataset to download and convert. Use 'all' to process all datasets."
    ), 
    out_dir: Path = typer.Argument(
        Path("data/uner"),
        help="The output directory where the files will be saved. "
             "Downloaded files will be saved in out_dir/raw/dataset_name "
             "Converted files will be saved in out_dir/processed/dataset_name"
    )
):  
    if dataset == UNERDataset.ALL:
        for dataset_name in REGISTRY.keys():
            language = get_language(dataset_name)
            raw_dir = out_dir / "raw" / dataset_name
            processed_dir = out_dir / "processed" / f"{dataset_name}-{language}"
            logger.info(f"Processing dataset: {dataset_name}")
            download(dataset=dataset_name, out_dir=raw_dir)
            format(in_dir=raw_dir, out_dir=processed_dir)
    else:
        raw_dir = out_dir / "raw" / dataset
        processed_dir = out_dir / "processed" / f"{dataset}-{language}"
        logger.info(f"Processing dataset: {dataset}")
        download(dataset=dataset, out_dir=raw_dir)
        format(in_dir=raw_dir, out_dir=processed_dir)


if __name__ == "__main__":
    app()