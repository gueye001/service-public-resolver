"""API web + demo pour l'assistant de resolution de questions administratives.

Pipeline : BGE-M3 -> FAISS (k=5) -> reranking CrossEncoder -> seuil calibre.
Si le meilleur score de reranking depasse le seuil : question "connue", renvoie
la reponse officielle historique. Sinon : "nouvelle", escalade recommandee.

Usage :  python api.py   (sert l'API + l'interface statique sur http://127.0.0.1:8000)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src import config
from src.query import IncidentResolver

app = FastAPI(title="Service Public Résolveur")

_metrics = json.loads((config.ROOT / "results" / "metrics.json").read_text(encoding="utf-8"))
_threshold = _metrics["threshold"]

resolver = IncidentResolver(threshold=_threshold)
_history: list[dict] = []


class ResolveRequest(BaseModel):
    question: str


class Candidate(BaseModel):
    question: str
    reponse: str
    theme: str
    score_faiss: float
    score_rerank: float


class ResolveResponse(BaseModel):
    id: int
    question: str
    status: str  # "known" | "novel"
    confidence: float
    reponse: str | None
    theme: str | None
    timestamp: str
    candidates: list[Candidate]


@app.get("/api/stats")
def get_stats():
    return _metrics


@app.get("/api/history")
def get_history():
    return list(reversed(_history))


@app.post("/api/resolve", response_model=ResolveResponse)
def resolve(req: ResolveRequest):
    question = (req.question or "").strip()
    result = resolver.resolve(question)
    best = result.candidates[0] if result.candidates else None

    entry = {
        "id": len(_history) + 1,
        "question": question,
        "status": result.status,
        "confidence": round(result.confidence, 3),
        "reponse": result.response,
        "theme": best.category if (result.status == "known" and best) else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candidates": [
            {
                "question": c.issue,
                "reponse": c.response,
                "theme": c.category,
                "score_faiss": round(c.faiss_score, 3),
                "score_rerank": round(c.rerank_score, 3),
            }
            for c in result.candidates
        ],
    }
    _history.append(entry)
    return entry


app.mount("/", StaticFiles(directory="web", html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
