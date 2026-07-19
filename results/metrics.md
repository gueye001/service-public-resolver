# Rapport de metriques — Résolveur Public

_Genere automatiquement par `src/evaluation.py`._

## Contexte d'evaluation
- Tickets de test : **3056** (2212 connus, 844 nouveaux)
- Nouveaute simulee : categorie **`Ressources humaines`** entierement retiree du train
- Embeddings : `BAAI/bge-m3` · Reranker : `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`
- k voisins : **5**

## Seuil calibre
Seuil optimal (max F1 macro) : **-2.728**
_Calibre empiriquement sur les scores de reranking du test set, pas fixe a la main._

| seuil | F1 macro | F1 connu | F1 nouveau |
|------:|---------:|---------:|-----------:|
| -2.728 | 0.639 | 0.765 | 0.512 |
| -2.726 | 0.638 | 0.765 | 0.512 |
| -2.743 | 0.638 | 0.765 | 0.511 |
| -2.721 | 0.638 | 0.765 | 0.511 |
| -2.704 | 0.638 | 0.764 | 0.512 |

## Detection connu vs nouveau

| Classe | Precision | Recall | F1 | Support |
|--------|----------:|-------:|---:|--------:|
| Connu    | 0.825 | 0.714 | 0.765 | 2212 |
| Nouveau  | 0.445 | 0.602 | 0.512 | 844 |
| **Macro F1** | | | **0.639** | |

### Matrice de confusion
|                | Predit connu | Predit nouveau |
|----------------|-------------:|---------------:|
| **Reel connu**   | 1579 | 633 |
| **Reel nouveau** | 336 | 508 |

## Qualite du rappel (cas connus)
- **Recall@5** : **0.973** — proportion de tickets connus dont la
  bonne categorie figure parmi les 5 voisins recuperes par FAISS.

## Lecture
- Un **F1 nouveau** eleve signifie que l'agent detecte fiablement les pannes inedites
  et les escalade au lieu de proposer une fausse solution.
- Un **Recall@5** eleve garantit que, quand le cas est connu, la bonne famille de
  solution est bien remontee avant reranking.
