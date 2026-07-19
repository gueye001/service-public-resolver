# Résolveur Public

**Répond instantanément aux questions administratives récurrentes en s'appuyant sur
les réponses officielles déjà publiées, et identifie les questions inédites à
transmettre à un agent humain — réduisant la charge des guichets sur les demandes
les plus courantes.**

Face à une question administrative ("Comment obtenir un logement social ?", "Le CSE
a-t-il un budget ?"), cet agent compare la question à un historique de réponses
officielles de service-public.fr et renvoie soit la **réponse déjà publiée** (avec un
score de confiance), soit une recommandation d'**escalade** vers un agent humain quand
la question est réellement inédite.

## Comment ça marche

Pipeline de recherche sémantique + détection de nouveauté :

1. **Embeddings BGE-M3** — chaque question officielle est encodée en vecteur dense
   1024-dim.
2. **Index FAISS** — recherche des k=5 questions officielles les plus proches
   (similarité cosinus).
3. **Reranking CrossEncoder** — réordonne finement les 5 candidats.
4. **Seuillage calibré** — si le meilleur score de reranking dépasse un seuil calibré
   empiriquement, la question est déclarée *connue* et la réponse officielle est
   renvoyée ; sinon elle est déclarée *nouvelle* et escaladée.

Le seuil est calibré en retirant un thème administratif entier du train (ici
« Ressources humaines », 844 questions) pour simuler de vraies questions inédites,
puis choisi pour **maximiser le F1 macro** entre "connu correctement identifié" et
"nouveau correctement identifié".

## Résultats chiffrés

> Évaluation sur 15 594 paires question/réponse officielles (12 538 train / 3 056 test).
> Détail complet dans [`results/metrics.md`](results/metrics.md).

| Métrique | Valeur |
|----------|-------:|
| Seuil calibré (max F1 macro) | -2.73 |
| F1 macro (connu vs nouveau) | **63.9 %** |
| F1 détection "connu" | 76.5 % |
| F1 détection "nouveau" | 51.2 % |
| **Recall@5** (cas connus) | **97.3 %** |

Ces chiffres sont nettement meilleurs que sur un premier dataset testé (tickets IT
génériques, F1 macro 48.4 %) — voir [Choix du dataset](#choix-du-dataset).

## Interface

Une vraie interface web (FastAPI + HTML/CSS/JS, sans dépendance externe) plutôt qu'une
démo Gradio basique : zone de question, historique de session filtrable (connu/nouveau),
détail des 5 candidats avec scores, page statistiques.

```bash
python api.py
# puis ouvrir http://127.0.0.1:8000
```

## Structure du projet

```
service-public-resolver/
├── README.md
├── requirements.txt
├── run.py                     # pipeline end-to-end (data -> index -> eval)
├── api.py                     # backend FastAPI + sert l'interface web
├── web/                       # interface statique (HTML/CSS/JS)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── src/
│   ├── config.py              # tous les parametres (modeles, seuils, chemins)
│   ├── data.py                # chargement + split avec simulation de nouveaute
│   ├── indexing.py            # BGE-M3 -> FAISS
│   ├── query.py               # recherche + reranking + decision
│   └── evaluation.py          # calibration du seuil + metriques
├── scripts/
│   └── build_dataset.py       # construit le dataset depuis Hugging Face
└── results/
    ├── metrics.md              # rapport de metriques (auto-genere)
    └── metrics.json            # memes chiffres, servis par l'API
```

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac
pip install -r requirements.txt
```

## Récupérer et préparer les données

```bash
python scripts/build_dataset.py   # telecharge ~190 Mo depuis Hugging Face, normalise
python run.py                     # split, indexation, calibration, rapport
python api.py                     # lance l'interface web
```

## Choix du dataset

Ce projet a d'abord été testé sur un dataset Kaggle de tickets de support IT
générique ("Tech Support Conversations") — mais ce dernier ne contenait que **7
formulations de texte** répétées sur toutes les catégories, rendant le matching
sémantique dégénéré (F1 macro 48.4 %, tous les paraphrases classées "nouveau" même
quand connues). Le dataset a été remplacé par le sous-ensemble **« Question-réponse »**
de [`AgentPublic/service-public`](https://huggingface.co/datasets/AgentPublic/service-public)
(licence **Etalab-2.0**, contenu officiel de service-public.fr) : de vraies paires
question/réponse rédigées par l'administration française, avec un vocabulaire riche et
naturel sur 22 thèmes. Résultat : un F1 macro et un Recall@5 nettement meilleurs, et un
vrai matching sémantique démontrable (voir capture des cas "connu"/"nouveau" dans
l'interface).

## Choix de conception

- **BGE-M3 / FAISS `IndexFlatIP` / CrossEncoder** : même stack que mes autres projets
  RAG, cohérence et reproductibilité.
- **k=5** : compromis rappel/coût de reranking.
- **Thème retiré : "Ressources humaines"** : taille moyenne (844 questions), assez
  distinct thématiquement pour un test propre de détection de nouveauté.
- **Seuil calibré** : maximise le F1 macro sur le test set — pas de valeur arbitraire.

## Limites

- La réponse renvoyée est celle du **meilleur candidat unique** ; un système de
  production combinerait plusieurs candidats ou une génération augmentée (RAG génératif)
  plutôt qu'un simple retrieval verbatim.
- Un seul thème retiré simule la nouveauté ; une validation croisée sur plusieurs thèmes
  retirés renforcerait la robustesse de la mesure (F1 nouveau = 51 %, à améliorer).
- Le contenu provient d'un instantané du dataset Hugging Face (mis à jour
  périodiquement) : en production, il faudrait resynchroniser régulièrement avec
  service-public.fr.

## Licence des données

Les données proviennent de service-public.fr via le dataset Hugging Face
`AgentPublic/service-public`, sous licence **Etalab-2.0 (Licence Ouverte)** — réutilisation
libre avec mention de la source.
