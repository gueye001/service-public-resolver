"""Configuration centralisee du projet.

Tous les choix de parametres (modeles, chemins, seuils, seed) sont regroupes ici
pour etre explicites et reproductibles.
"""
from __future__ import annotations

from pathlib import Path

# --- Chemins ---------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
ARTIFACTS_DIR = DATA_DIR / "artifacts"

# Dataset : paires question/reponse officielles de service-public.fr,
# normalisees par scripts/build_dataset.py.
RAW_CSV = DATA_DIR / "service_public_fr.csv"

# --- Modeles ---------------------------------------------------------------
EMBEDDING_MODEL = "BAAI/bge-m3"
RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

# --- Parametres pipeline ---------------------------------------------------
K_NEIGHBORS = 5
SEED = 42
TEST_SIZE = 0.15

# Theme entierement retire du train pour simuler des questions VRAIMENT
# inedites. Choisi apres exploration : taille moyenne (844 questions), assez
# distinct thematiquement des autres themes pour un test propre.
NOVEL_CATEGORY = "Ressources humaines"

# Schema du dataset (memes noms que it-incident-resolver, code reutilise tel quel).
COL_ID = "Conversation_ID"
COL_ISSUE = "Customer_Issue"      # ici : la question posee par l'usager
COL_RESPONSE = "Tech_Response"    # ici : la reponse officielle
COL_TIME = "Resolution_Time"
COL_CATEGORY = "Issue_Category"   # ici : le theme administratif
COL_STATUS = "Issue_Status"
