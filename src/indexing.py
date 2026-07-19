"""Pipeline d'indexation : BGE-M3 -> FAISS.

On encode les Customer_Issue du train set, on normalise les vecteurs (L2) et on
les stocke dans un IndexFlatIP. Sur des vecteurs normalises, l'inner product
equivaut a la similarite cosinus -> scores dans [-1, 1], interpretables.
"""
from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np
import pandas as pd

from . import config


def get_embedder(model_name: str = config.EMBEDDING_MODEL):
    """Charge le modele d'embedding (mise en cache par sentence-transformers)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def encode_issues(texts, embedder=None, batch_size: int = 32, show_progress=True):
    """Encode une liste de textes en vecteurs normalises float32."""
    if embedder is None:
        embedder = get_embedder()
    emb = embedder.encode(
        list(texts),
        batch_size=batch_size,
        normalize_embeddings=True,  # -> cosinus via inner product
        show_progress_bar=show_progress,
        convert_to_numpy=True,
    )
    return emb.astype("float32")


def build_index(train_df: pd.DataFrame, embedder=None, out_dir: Path = config.ARTIFACTS_DIR):
    """Construit et serialise l'index FAISS + les metadonnees du train.

    Sauvegarde :
      - index.faiss    : l'index vectoriel
      - meta.parquet   : issue / response / category / status alignes sur l'index
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    embeddings = encode_issues(train_df[config.COL_ISSUE].tolist(), embedder)
    dim = embeddings.shape[1]

    index = faiss.IndexFlatIP(dim)  # exact, adapte a ~1600 vecteurs
    index.add(embeddings)

    faiss.write_index(index, str(out_dir / "index.faiss"))

    meta = train_df[
        [config.COL_ID, config.COL_ISSUE, config.COL_RESPONSE,
         config.COL_CATEGORY, config.COL_STATUS]
    ].reset_index(drop=True)
    meta.to_parquet(out_dir / "meta.parquet")

    (out_dir / "index_info.json").write_text(
        json.dumps({"n_vectors": int(index.ntotal), "dim": int(dim),
                    "embedding_model": config.EMBEDDING_MODEL}, indent=2)
    )
    print(f"[index] {index.ntotal} tickets indexes, dim={dim} -> {out_dir}")
    return index, meta


def load_index(out_dir: Path = config.ARTIFACTS_DIR):
    """Recharge (index FAISS, metadonnees) depuis le disque."""
    out_dir = Path(out_dir)
    index = faiss.read_index(str(out_dir / "index.faiss"))
    meta = pd.read_parquet(out_dir / "meta.parquet")
    return index, meta


if __name__ == "__main__":
    # Usage: python -m src.indexing  (construit l'index depuis le dataset)
    from .data import load_dataset, train_test_split_with_novelty

    df = load_dataset()
    train_df, _ = train_test_split_with_novelty(df)
    build_index(train_df)
