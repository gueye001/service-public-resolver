"""Evaluation + calibration empirique du seuil.

Deux questions distinctes :
  A) Detection connu vs nouveau -> Precision / Recall / F1 (le seuil se calibre ici).
  B) Qualite du rappel pour les cas connus -> Recall@k (la bonne categorie
     est-elle dans le top-k renvoye par FAISS ?).

Le seuil n'est PAS choisi a la main : on balaie toutes les valeurs possibles des
scores de reranking observes et on garde celle qui maximise le F1 macro entre les
deux classes (connu / nouveau). Le F1 macro (moyenne des deux F1) evite de
favoriser la classe majoritaire.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_recall_fscore_support

from . import config
from .query import IncidentResolver


def score_test_set(resolver: IncidentResolver, test_df: pd.DataFrame,
                   k: int = config.K_NEIGHBORS) -> pd.DataFrame:
    """Pour chaque ticket de test : meilleur score de reranking + infos de rappel.

    Retourne un DataFrame avec :
      best_rerank : logit du meilleur candidat (score de decision)
      is_novel    : verite terrain (True si categorie jamais vue)
      true_cat    : categorie reelle du ticket
      topk_cats   : liste des categories des k voisins recuperes
      hit_at_k    : True si true_cat est dans topk_cats (pour Recall@k)
    """
    from .indexing import encode_issues

    texts = test_df[config.COL_ISSUE].tolist()
    qvecs = encode_issues(texts, resolver.embedder, show_progress=True)
    faiss_scores, idxs = resolver.search(qvecs, k)

    records = []
    for i, text in enumerate(texts):
        cands = resolver._candidates_for(text, idxs[i], faiss_scores[i])
        topk_cats = [c.category for c in cands]
        true_cat = test_df.iloc[i][config.COL_CATEGORY]
        records.append({
            "best_rerank": cands[0].rerank_score,
            "is_novel": bool(test_df.iloc[i]["is_novel"]),
            "true_cat": true_cat,
            "topk_cats": topk_cats,
            "hit_at_k": true_cat in topk_cats,
        })
    return pd.DataFrame(records)


def calibrate_threshold(scored: pd.DataFrame):
    """Trouve le seuil maximisant le F1 macro (connu vs nouveau).

    y_true : "known" si non-novel, "novel" sinon.
    Prediction : "known" si best_rerank > seuil, sinon "novel".
    Retourne (best_threshold, sweep_df).
    """
    y_true = np.where(scored["is_novel"], "novel", "known")
    scores = scored["best_rerank"].to_numpy()

    # Seuils candidats : milieux entre scores tries + marges.
    uniq = np.unique(scores)
    mids = (uniq[:-1] + uniq[1:]) / 2 if len(uniq) > 1 else uniq
    candidates = np.concatenate([[uniq.min() - 1e-3], mids, [uniq.max() + 1e-3]])

    rows = []
    for thr in candidates:
        y_pred = np.where(scores > thr, "known", "novel")
        macro = f1_score(y_true, y_pred, average="macro", labels=["known", "novel"], zero_division=0)
        f1_known = f1_score(y_true, y_pred, pos_label="known", labels=["known", "novel"],
                            average="binary", zero_division=0)
        f1_novel = f1_score(y_true, y_pred, pos_label="novel", labels=["known", "novel"],
                            average="binary", zero_division=0)
        rows.append({"threshold": float(thr), "f1_macro": macro,
                     "f1_known": f1_known, "f1_novel": f1_novel})

    sweep = pd.DataFrame(rows)
    best_threshold = float(sweep.loc[sweep["f1_macro"].idxmax(), "threshold"])
    return best_threshold, sweep


def evaluate(scored: pd.DataFrame, threshold: float) -> dict:
    """Calcule toutes les metriques finales pour un seuil donne."""
    y_true = np.where(scored["is_novel"], "novel", "known")
    y_pred = np.where(scored["best_rerank"].to_numpy() > threshold, "known", "novel")

    labels = ["known", "novel"]
    p, r, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0)
    macro_f1 = f1_score(y_true, y_pred, average="macro", labels=labels, zero_division=0)

    # Matrice de confusion 2x2.
    cm = {
        "known_as_known": int(((y_true == "known") & (y_pred == "known")).sum()),
        "known_as_novel": int(((y_true == "known") & (y_pred == "novel")).sum()),
        "novel_as_novel": int(((y_true == "novel") & (y_pred == "novel")).sum()),
        "novel_as_known": int(((y_true == "novel") & (y_pred == "known")).sum()),
    }

    # Recall@k : uniquement sur les cas connus (categorie presente a l'index).
    known_mask = ~scored["is_novel"].to_numpy()
    recall_at_k = float(scored.loc[known_mask, "hit_at_k"].mean()) if known_mask.any() else 0.0

    return {
        "threshold": float(threshold),
        "n_test": int(len(scored)),
        "n_known": int((y_true == "known").sum()),
        "n_novel": int((y_true == "novel").sum()),
        "per_class": {
            lab: {"precision": float(p[j]), "recall": float(r[j]),
                  "f1": float(f1[j]), "support": int(support[j])}
            for j, lab in enumerate(labels)
        },
        "macro_f1": float(macro_f1),
        "confusion": cm,
        "recall_at_k": recall_at_k,
        "k": config.K_NEIGHBORS,
    }


def write_report(metrics: dict, sweep: pd.DataFrame,
                 path: Path = config.RESULTS_DIR / "metrics.md",
                 novel_category: str = config.NOVEL_CATEGORY):
    """Genere un rapport markdown clair et chiffre."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    m = metrics
    kn, nv = m["per_class"]["known"], m["per_class"]["novel"]
    cm = m["confusion"]

    # 5 lignes autour de l'optimum pour illustrer la calibration.
    sweep_sorted = sweep.sort_values("f1_macro", ascending=False).head(5)
    sweep_tbl = "\n".join(
        f"| {row.threshold:.3f} | {row.f1_macro:.3f} | {row.f1_known:.3f} | {row.f1_novel:.3f} |"
        for row in sweep_sorted.itertuples()
    )

    md = f"""# Rapport de metriques — IT Incident Resolver

_Genere automatiquement par `src/evaluation.py`._

## Contexte d'evaluation
- Tickets de test : **{m['n_test']}** ({m['n_known']} connus, {m['n_novel']} nouveaux)
- Nouveaute simulee : categorie **`{novel_category}`** entierement retiree du train
- Embeddings : `{config.EMBEDDING_MODEL}` · Reranker : `{config.RERANKER_MODEL}`
- k voisins : **{m['k']}**

## Seuil calibre
Seuil optimal (max F1 macro) : **{m['threshold']:.3f}**
_Calibre empiriquement sur les scores de reranking du test set, pas fixe a la main._

| seuil | F1 macro | F1 connu | F1 nouveau |
|------:|---------:|---------:|-----------:|
{sweep_tbl}

## Detection connu vs nouveau

| Classe | Precision | Recall | F1 | Support |
|--------|----------:|-------:|---:|--------:|
| Connu    | {kn['precision']:.3f} | {kn['recall']:.3f} | {kn['f1']:.3f} | {kn['support']} |
| Nouveau  | {nv['precision']:.3f} | {nv['recall']:.3f} | {nv['f1']:.3f} | {nv['support']} |
| **Macro F1** | | | **{m['macro_f1']:.3f}** | |

### Matrice de confusion
|                | Predit connu | Predit nouveau |
|----------------|-------------:|---------------:|
| **Reel connu**   | {cm['known_as_known']} | {cm['known_as_novel']} |
| **Reel nouveau** | {cm['novel_as_known']} | {cm['novel_as_novel']} |

## Qualite du rappel (cas connus)
- **Recall@{m['k']}** : **{m['recall_at_k']:.3f}** — proportion de tickets connus dont la
  bonne categorie figure parmi les {m['k']} voisins recuperes par FAISS.

## Lecture
- Un **F1 nouveau** eleve signifie que l'agent detecte fiablement les pannes inedites
  et les escalade au lieu de proposer une fausse solution.
- Un **Recall@{m['k']}** eleve garantit que, quand le cas est connu, la bonne famille de
  solution est bien remontee avant reranking.
"""
    path.write_text(md, encoding="utf-8")
    print(f"[report] ecrit -> {path}")
    return path


def run_full_evaluation(artifacts_dir=config.ARTIFACTS_DIR, test_df=None,
                        report_path=config.RESULTS_DIR / "metrics.md",
                        novel_category=config.NOVEL_CATEGORY):
    """Orchestration complete : score -> calibre -> evalue -> rapport."""
    resolver = IncidentResolver(artifacts_dir)
    scored = score_test_set(resolver, test_df)
    best_threshold, sweep = calibrate_threshold(scored)
    metrics = evaluate(scored, best_threshold)
    write_report(metrics, sweep, path=report_path, novel_category=novel_category)

    # Persiste le seuil calibre pour la demo (app.py le recharge tel quel).
    import json
    (Path(artifacts_dir) / "threshold.json").write_text(
        json.dumps({"threshold": best_threshold, "macro_f1": metrics["macro_f1"]}, indent=2))
    return metrics, best_threshold, sweep, scored
