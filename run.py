"""Orchestrateur end-to-end : data -> split -> index -> evaluation -> rapport.

Usage :  python run.py
Prerequis :  python scripts/build_dataset.py
"""
from __future__ import annotations

from src import config
from src.data import load_dataset, train_test_split_with_novelty
from src.evaluation import run_full_evaluation
from src.indexing import build_index, get_embedder


def main():
    df = load_dataset()
    print(f"[data] {len(df)} questions, {df[config.COL_CATEGORY].nunique()} themes")

    train_df, test_df = train_test_split_with_novelty(df)
    print(f"[split] train={len(train_df)}  test={len(test_df)} "
          f"(nouveaux={int(test_df['is_novel'].sum())})")

    embedder = get_embedder()
    build_index(train_df, embedder)

    metrics, thr, _, _ = run_full_evaluation(test_df=test_df)
    print(f"\n[resultat] seuil={thr:.3f}  F1_macro={metrics['macro_f1']:.3f}  "
          f"Recall@{metrics['k']}={metrics['recall_at_k']:.3f}")


if __name__ == "__main__":
    main()
