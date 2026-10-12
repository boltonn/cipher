from pathlib import Path

import numpy as np
import torch
from clir.models.pytorch import TextEmbeddingPytorchModel
from clir.utils.chunk import get_chunker
from clir.utils.embedding import normalize
from langchain_text_splitters import RecursiveCharacterTextSplitter

model_dir = Path.home() / "models" / "transformers" / "jina-embeddings-v5-text-small"
model = TextEmbeddingPytorchModel(model_dir=model_dir, device="cuda")

chunker: RecursiveCharacterTextSplitter = get_chunker(
    tokenizer=model.tokenizer,
    chunk_size=512,
    chunk_overlap=0,
)

text = "Overview of climate change impacts on coastal cities"
query_embeddings = (
    model.model.encode(
        texts=[text],
        task="retrieval",
        prompt_name="query",
    )
    .to(torch.float32)
    .cpu()
    .numpy()
)

max_chunks = 10
chunks = chunker.split_text(text=text)[:max_chunks]
model_inputs = model.preprocess(chunks, is_query=True, task="retrieval")
embeddings = model.infer(model_inputs)

embedding = embeddings[0]
np.linalg.norm(embedding)

np.linalg.norm(normalize(embedding))
