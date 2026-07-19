"""Chargement des donnees et split train/test avec simulation de nouveaute.

Point cle du projet : pour evaluer *proprement* la detection de nouveaute, on
retire un theme administratif ENTIER du train. Le modele n'a alors jamais vu ce
type de question a l'indexation -> ces questions sont de vrais cas inedits au
moment du test.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config


REQUIRED_COLS = [
    config.COL_ID,
    config.COL_ISSUE,
    config.COL_RESPONSE,
    config.COL_CATEGORY,
    config.COL_STATUS,
]


def load_dataset(path=config.RAW_CSV) -> pd.DataFrame:
    """Charge le CSV normalise et valide le schema."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset introuvable: {path}\n"
            "-> Lance: python scripts/build_dataset.py"
        )

    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Colonnes manquantes dans {path.name}: {missing}\n"
            f"Colonnes trouvees: {list(df.columns)}"
        )
    return _clean(df)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoyage minimal : supprime les lignes sans question/reponse, deduplique."""
    df = df.copy()
    df[config.COL_ISSUE] = df[config.COL_ISSUE].astype(str).str.strip()
    df[config.COL_RESPONSE] = df[config.COL_RESPONSE].astype(str).str.strip()
    df = df[df[config.COL_ISSUE].str.len() > 0]
    df = df.dropna(subset=[config.COL_ISSUE, config.COL_CATEGORY])
    df = df.drop_duplicates(subset=[config.COL_ID]).reset_index(drop=True)
    return df


def train_test_split_with_novelty(
    df: pd.DataFrame,
    test_size: float = config.TEST_SIZE,
    novel_category: str = config.NOVEL_CATEGORY,
    seed: int = config.SEED,
):
    """Split train/test avec injection de nouveaute.

    - TOUTES les questions de `novel_category` sont retirees du train et
      placees dans le test, etiquetees is_novel=True (theme jamais vu a
      l'indexation).
    - Parmi les autres themes, on echantillonne ~`test_size` comme cas de
      test "connus" (is_novel=False) ; le reste forme le train (index).

    Retourne (train_df, test_df) ou test_df porte une colonne booleenne `is_novel`.
    """
    rng = np.random.default_rng(seed)
    df = df.reset_index(drop=True)

    is_novel_cat = df[config.COL_CATEGORY] == novel_category
    novel_df = df[is_novel_cat].copy()
    known_df = df[~is_novel_cat].copy()

    if len(novel_df) == 0:
        raise ValueError(
            f"Theme '{novel_category}' absent. Themes dispo: "
            f"{sorted(df[config.COL_CATEGORY].unique())}"
        )

    # Echantillon stratifie par theme pour les cas "connus" de test.
    test_known_idx = []
    for _, group in known_df.groupby(config.COL_CATEGORY):
        n_test = max(1, int(round(len(group) * test_size)))
        picked = rng.choice(group.index.values, size=n_test, replace=False)
        test_known_idx.extend(picked.tolist())

    test_known_df = known_df.loc[test_known_idx].copy()
    train_df = known_df.drop(index=test_known_idx).reset_index(drop=True)

    test_known_df["is_novel"] = False
    novel_df["is_novel"] = True
    test_df = (
        pd.concat([test_known_df, novel_df], ignore_index=True)
        .sample(frac=1.0, random_state=seed)  # melange
        .reset_index(drop=True)
    )

    return train_df, test_df
