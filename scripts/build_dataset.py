"""Construit le dataset a partir de 'AgentPublic/service-public' (HuggingFace),
contenu officiel de service-public.fr, licence Etalab-2.0 (licence ouverte).

Le sous-type 'Question-reponse' du dataset stocke, pour chaque chunk :
  - context[-1]  : la question posee (ex. "Le CSE beneficie-t-il d'un budget ?")
  - text         : la reponse officielle correspondante

Renormalise vers le schema utilise par tout le pipeline (Conversation_ID,
Customer_Issue, Tech_Response, Resolution_Time, Issue_Category, Issue_Status).

Usage :
  python scripts/build_dataset.py
(telecharge automatiquement le parquet source depuis le Hugging Face Hub, ~190 Mo)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402

HF_REPO = "AgentPublic/service-public"
HF_FILE = "data/service-public-latest/service_public_part_0.parquet"

ATTRIBUTION = (
    "Source: service-public.fr via le dataset Hugging Face 'AgentPublic/service-public', "
    "licence Etalab-2.0 (Licence Ouverte). Contenu officiel de l'administration francaise."
)


def download_source() -> Path:
    from huggingface_hub import hf_hub_download

    scratch = config.DATA_DIR / "_scratch"
    print(f"[hf] telechargement de {HF_REPO} ({HF_FILE}) ...")
    path = hf_hub_download(repo_id=HF_REPO, repo_type="dataset", filename=HF_FILE,
                            local_dir=str(scratch))
    return Path(path)


def main():
    scratch_file = config.DATA_DIR / "_scratch" / HF_FILE
    src_path = scratch_file if scratch_file.exists() else download_source()

    cols = ["doc_id", "theme", "context", "text"]
    df = pd.read_parquet(src_path, columns=cols)

    # Ne garder que les chunks question-reponse reels (context non vide).
    df = df[df["context"].apply(lambda x: len(x) > 0)].copy()
    df["question"] = df["context"].apply(lambda x: str(x[-1]).strip())
    df["theme_clean"] = df["theme"].apply(
        lambda t: t.split(",")[0].strip() if isinstance(t, str) else t
    )

    # Filtre qualite : certains context[-1] sont des libelles de conditions
    # imbriquees (ex. "Au sein de l'UE") et non de vraies questions -> on ne
    # garde que ceux se terminant par '?', et un theme non vide.
    df = df[df["question"].str.endswith("?")]
    df = df[df["theme_clean"].notna() & (df["theme_clean"].str.strip() != "")]

    # Deduplique sur (question, reponse) exacte -> garde la diversite reelle.
    df = df.drop_duplicates(subset=["question", "text"]).reset_index(drop=True)

    out = pd.DataFrame({
        config.COL_ID: [f"SP-{i:04d}" for i in range(len(df))],
        config.COL_ISSUE: df["question"],
        config.COL_RESPONSE: df["text"].astype(str).str.strip(),
        config.COL_TIME: pd.NA,
        config.COL_CATEGORY: df["theme_clean"],
        config.COL_STATUS: "Resolved",
    })

    config.RAW_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(config.RAW_CSV, index=False, encoding="utf-8")
    print(f"[ok] {len(out)} paires question/reponse -> {config.RAW_CSV}")
    print(f"[attribution] {ATTRIBUTION}")
    print("\nThemes disponibles:")
    print(out[config.COL_CATEGORY].value_counts())


if __name__ == "__main__":
    main()
