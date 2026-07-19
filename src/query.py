"""Pipeline de requete : recherche + reranking + decision connu/nouveau.

Etapes pour un nouveau ticket :
  1. Embedding BGE-M3 du ticket
  2. Recherche des k plus proches voisins dans l'index FAISS
  3. Reranking des k candidats avec un CrossEncoder (paires (ticket, issue_hist))
  4. Decision : si score de reranking du meilleur candidat > seuil -> "connu"
     (on renvoie le Tech_Response historique) ; sinon -> "nouveau" (escalade).

Le seuil est calibre empiriquement (voir src/evaluation.py), pas fixe a la main.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import config
from .indexing import encode_issues, get_embedder, load_index


@dataclass
class Candidate:
    issue: str
    response: str
    category: str
    status: str
    faiss_score: float   # similarite cosinus (rappel dense)
    rerank_score: float  # logit CrossEncoder (precision fine)


@dataclass
class Resolution:
    status: str          # "known" ou "novel"
    confidence: float    # rerank_score du meilleur candidat
    response: str | None
    candidates: list = field(default_factory=list)


class IncidentResolver:
    """Charge les modeles + l'index et resout un ticket entrant."""

    def __init__(self, artifacts_dir: Path = config.ARTIFACTS_DIR, threshold: float | None = None):
        self.index, self.meta = load_index(artifacts_dir)
        self.embedder = get_embedder()
        self._cross_encoder = None  # lazy load
        self.threshold = threshold  # peut etre defini apres calibration

    @property
    def cross_encoder(self):
        if self._cross_encoder is None:
            from sentence_transformers import CrossEncoder
            self._cross_encoder = CrossEncoder(config.RERANKER_MODEL)
        return self._cross_encoder

    # --- briques bas niveau ------------------------------------------------
    def search(self, query_vecs: np.ndarray, k: int = config.K_NEIGHBORS):
        """Recherche FAISS batch. Retourne (scores, indices)."""
        return self.index.search(query_vecs.astype("float32"), k)

    def _candidates_for(self, ticket_text: str, idx_row: np.ndarray, faiss_scores: np.ndarray):
        """Construit et rerank les candidats pour un ticket."""
        rows = self.meta.iloc[idx_row]
        pairs = [(ticket_text, issue) for issue in rows[config.COL_ISSUE].tolist()]
        rr = self.cross_encoder.predict(pairs)
        cands = [
            Candidate(
                issue=r[config.COL_ISSUE],
                response=r[config.COL_RESPONSE],
                category=r[config.COL_CATEGORY],
                status=r[config.COL_STATUS],
                faiss_score=float(fs),
                rerank_score=float(score),
            )
            for (_, r), fs, score in zip(rows.iterrows(), faiss_scores, rr)
        ]
        cands.sort(key=lambda c: c.rerank_score, reverse=True)
        return cands

    def retrieve_and_rerank(self, ticket_text: str, k: int = config.K_NEIGHBORS):
        """Retourne les candidats reranks (sans appliquer le seuil)."""
        qvec = encode_issues([ticket_text], self.embedder, show_progress=False)
        scores, idx = self.search(qvec, k)
        return self._candidates_for(ticket_text, idx[0], scores[0])

    # --- API haut niveau ---------------------------------------------------
    def resolve(self, ticket_text: str, k: int = config.K_NEIGHBORS,
                threshold: float | None = None) -> Resolution:
        """Resout un ticket : renvoie la solution historique ou une escalade."""
        thr = threshold if threshold is not None else self.threshold
        if thr is None:
            raise ValueError("Aucun seuil defini. Calibrer via src/evaluation.py.")

        cands = self.retrieve_and_rerank(ticket_text, k)
        best = cands[0]
        if best.rerank_score > thr:
            return Resolution("known", best.rerank_score, best.response, cands)
        return Resolution("novel", best.rerank_score, None, cands)
