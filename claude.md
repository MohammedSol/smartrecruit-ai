# SmartRecruit AI — Fichier de Contexte Global

> **Usage** : Ce fichier est la mémoire centrale du projet. Il sert de System Prompt pour toutes les sessions de développement IA. Toute décision architecturale, toute contrainte technique, et tout l'état d'avancement y sont consignés.
> **Règle absolue** : Ne jamais générer de code sans avoir lu et respecté ce fichier dans son intégralité.

---

## 1. Vision du Projet

| Champ | Valeur |
|---|---|
| **Nom** | SmartRecruit AI |
| **Type** | Projet de Fin d'Études (PFA) — Ingénierie IA & Data Science |
| **Statut** | En cours de développement — Phase 0 validée |
| **Objectif** | Créer un ATS (Applicant Tracking System) augmenté par un moteur de recherche sémantique et un pipeline RAG (Retrieval-Augmented Generation), permettant à un recruteur d'interroger une base de CVs en langage naturel et d'obtenir une réponse contextuelle générée par un LLM. |

---

## 2. Stack Technique

### 2.1 Langage & Environnement

| Composant | Choix | Détail |
|---|---|---|
| **Langage** | Python 3.11 | Interpréteur Windows natif — `C:\Users\user\AppData\Local\Programs\Python\Python311` |
| **Environnement virtuel** | `.venv` | Créé avec Python 3.11 Windows natif (NOT MSYS2). Activation : `.venv\Scripts\Activate.ps1` |
| **Configuration** | `python-dotenv` | Toutes les variables passent par `.env` → `config/settings.py` |

### 2.2 Infrastructure (Docker)

> **Kafka est configuré en mode KRaft — sans aucune dépendance à Zookeeper.**

| Service | Image Docker | Port exposé | Rôle |
|---|---|---|---|
| **Kafka** | `confluentinc/cp-kafka:7.5.0` (KRaft) | `9092` | Broker de messages — ingestion des CVs |
| **MongoDB** | `mongo:7.0` | `27017` | Stockage documentaire des CVs complets |
| **Réseau** | `smartrecruit-net` (bridge) | — | Réseau Docker interne partagé |

> Kafka est le seul service d'infrastructure réseau. ChromaDB est utilisé **en mode in-process** (librairie Python, pas de conteneur).

### 2.3 Bases de Données

| BDD | Mode | Rôle dans l'architecture |
|---|---|---|
| **MongoDB** | Conteneur Docker (`localhost:27017`) | Stockage des CVs complets au format JSON/BSON. Un document = un CV. Interrogé par le RAG pour retourner les profils complets. |
| **ChromaDB** | In-process (lib Python) | Stockage vectoriel local. Persistance dans `./chroma_data/`. Utilisé pour la recherche par similarité sémantique (distance Cosinus). |

### 2.4 IA & RAG

| Composant | Choix technique | Détail |
|---|---|---|
| **Modèle d'embedding** | `paraphrase-multilingual-MiniLM-L12-v2` | Via `sentence-transformers`. Vecteurs de 384 dimensions. Modèle **multilingue** (FR/EN/AR/etc.) — remplace `all-MiniLM-L6-v2` après validation du problème cross-lingual. |
| **Orchestration RAG** | `LangChain` + **GraphRAG** | Pipeline Retrieve → Augment → Generate. Architecture Hybrid GraphRAG (pattern Microsoft Research). |
| **LLM Provider** | **API Groq** | Gratuit en tier libre, très rapide. Modèle : `llama3-70b-8192`. Clé dans `.env` (`GROQ_API_KEY`). |
| **Vectorisation** | `sentence-transformers` + `torch` | Backend PyTorch (CPU). Pas de GPU requis pour ce projet. |

### 2.5 Front-end

| Composant | Choix | Détail |
|---|---|---|
| **Interface** | `Streamlit` | Dashboard B2B. Port `8501`. Lancé avec `streamlit run interface/app.py`. |
| **Result Cards** | HTML/CSS injectés dynamiquement | Via `st.markdown(..., unsafe_allow_html=True)` dans `interface/components/result_card.py`. |

---

## 3. Structure du Projet (Arborescence Canonique)

```
smartrecruit-ai/
│
├── claude.md                   ← CE FICHIER — Contexte global projet
├── docker-compose.yml          ← Infrastructure Kafka (KRaft) + MongoDB
├── requirements.txt            ← Dépendances Python verrouillées
├── .env                        ← Variables d'env réelles (NON versionné)
├── .env.example                ← Template public des variables d'env
├── .gitignore
├── README.md
│
├── config/
│   └── settings.py             ← SINGLE SOURCE OF TRUTH — Toutes les constantes
│
├── data/
│   ├── sample_cvs/             ← CVs JSON générés (tests)
│   └── raw/                    ← Dataset Kaggle brut (NON versionné)
│
├── ingestion/
│   ├── __init__.py
│   ├── producer.py             ← Lit les CVs JSON → publie sur Kafka topic
│   └── consumer.py             ← Consomme Kafka → Mongo → ChromaDB (Phase 1+2)
│
├── processing/
│   ├── __init__.py
│   ├── chunking.py             ← Découpe un CV JSON en sections textuelles
│   └── embeddings.py           ← Génère les vecteurs (multilingue, 384 dims)
│
├── generation/                 ← [NOUVEAU Phase 3] Couche LLM
│   ├── __init__.py
│   └── llm_client.py           ← Client Groq (generate_text + extract_json)
│
├── graph/                      ← [NOUVEAU Phase 3] Pipeline GraphRAG
│   ├── __init__.py
│   ├── entity_extractor.py     ← LLM → entités/relations JSON depuis MongoDB
│   ├── graph_builder.py        ← Construit le graphe NetworkX (in-memory)
│   ├── community_detector.py   ← Détecte les communautés (Louvain/Leiden)
│   └── community_summarizer.py ← LLM → résumé de chaque communauté
│
├── rag/
│   ├── __init__.py
│   ├── retriever.py            ← Cherche dans ChromaDB → récupère dans Mongo
│   ├── chain.py                ← Pipeline hybride (vectoriel + graphe)
│   └── prompts.py              ← Templates de prompts structurés
│
├── storage/
│   ├── __init__.py
│   ├── mongo_client.py         ← Client MongoDB (connexion + CRUD)
│   └── chroma_client.py        ← Client ChromaDB (collection + add + query)
│
├── interface/
│   ├── app.py                  ← Application Streamlit principale
│   └── components/
│       └── result_card.py      ← Carte profil HTML/CSS
│
├── scripts/
│   ├── generate_fake_cvs.py
│   ├── prepare_kaggle_data.py
│   ├── audit_chroma.py         ← Diagnostic READ-ONLY ChromaDB
│   └── test_chroma_search.py   ← Test interactif recherche semantique
│
├── tests/
│   ├── test_embeddings.py
│   ├── test_chunking.py
│   ├── test_mongo.py
│   └── test_chroma.py
│
└── chroma_data/                ← Données vectorielles locales (NON versionné)
```

---

## 4. Variables d'Environnement (`.env`)

> Le fichier `.env` est chargé **exclusivement** via `config/settings.py`. Aucun `os.getenv()` ne doit apparaître ailleurs dans le projet.

```env
# --- Kafka (KRaft) ---
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=cv-ingestion

# --- MongoDB ---
MONGO_URI=mongodb://admin:smartrecruit2026@localhost:27017
MONGO_DB_NAME=smartrecruit
MONGO_COLLECTION=cvs

# --- ChromaDB (in-process) ---
CHROMA_PERSIST_DIR=./chroma_data
CHROMA_COLLECTION=cv_embeddings

# --- Embeddings ---
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2

# --- LLM (Groq) ---
LLM_PROVIDER=groq
LLM_MODEL=llama3-70b-8192
GROQ_API_KEY=gsk_...

# --- Streamlit ---
STREAMLIT_PORT=8501
```

---

## 5. Principes d'Ingénierie — Règles Strictes

Ces règles sont **non négociables** pour toutes les sessions de développement.

### R1 — Développement Itératif
> Ne jamais générer le code d'une phase future sans validation explicite de la phase en cours. Chaque étape se termine par un critère de validation concret et vérifiable.

### R2 — Découplage des Responsabilités (SRP)
> Chaque module a **une seule responsabilité**.
> - Le `Producer` ne sait pas ce que fait le `Consumer`.
> - `storage/` isole les clients BDD — si on change de BDD, on ne touche qu'un fichier.
> - `processing/` ne connaît pas Kafka ni MongoDB.

### R3 — Single Source of Truth pour la Configuration
> Toute la configuration (URIs, ports, noms de collections, modèles, clés API) passe **exclusivement** par `config/settings.py`.
> ```python
> # CORRECT
> from config.settings import KAFKA_TOPIC
>
> # INTERDIT — ne jamais faire ça dans un module métier
> import os
> topic = os.getenv("KAFKA_TOPIC")
> ```

### R4 — Format JSON Canonique des CVs
> Tout CV dans ce système doit respecter ce schéma exact :
> ```json
> {
>   "id": "cv-001",
>   "name": "Marie Dupont",
>   "email": "marie.dupont@email.com",
>   "phone": "+33 6 12 34 56 78",
>   "title": "Développeuse Full Stack",
>   "summary": "5 ans d'expérience en développement web...",
>   "skills": ["Python", "Django", "React", "PostgreSQL", "Docker"],
>   "experience": [
>     {
>       "company": "TechCorp",
>       "role": "Développeuse Senior",
>       "duration": "2022-2025",
>       "description": "Développement d'une plateforme SaaS..."
>     }
>   ],
>   "education": [
>     {
>       "institution": "Université Paris-Saclay",
>       "degree": "Master Informatique",
>       "year": "2020"
>     }
>   ],
>   "languages": ["Français", "Anglais"],
>   "location": "Paris, France"
> }
> ```

### R5 — Kafka en Mode KRaft Uniquement
> Le `docker-compose.yml` ne doit **jamais** inclure un service Zookeeper. Kafka est configuré en mode KRaft (auto-géré). Toute image Kafka utilisée doit supporter KRaft nativement.

---

## 6. Roadmap d'Implémentation

### Phase 0 — Fondations & Données ✅ VALIDEE

| Sous-étape | Statut | Livrable |
|---|---|---|
| Arborescence complète du projet | ✅ | Tous les dossiers et fichiers créés |
| `docker-compose.yml` (Kafka KRaft + MongoDB) | ✅ | 2 conteneurs `Healthy` |
| Environnement Python 3.11 + `.venv` | ✅ | Venv Windows natif |
| `config/settings.py` | ✅ | Chargement centralisé validé |
| `scripts/prepare_kaggle_data.py` | ✅ | 50 CVs JSON dans `data/sample_cvs/` |

---

### Phase 1 — Pipeline de Données (Ingestion) ✅ VALIDEE

**Objectif** : Faire circuler un CV JSON de son fichier source jusqu'à MongoDB, via Kafka.

| Sous-étape | Statut | Livrable |
|---|---|---|
| `ingestion/producer.py` | ✅ | Publie 50 CVs sur le topic `cv_ingestion` |
| `ingestion/consumer.py` | ✅ | Consomme et persiste les CVs dans MongoDB (upsert idempotent) |

**Critère validé** : 50 CVs dans MongoDB, pipeline Producer → Consumer fonctionnel.

---

### Phase 2 — Vectorisation (Moteur de Recherche) ✅ VALIDEE

**Objectif** : Transformer chaque CV en vecteurs sémantiques indexés dans ChromaDB.

| Sous-étape | Statut | Livrable |
|---|---|---|
| `processing/chunking.py` | ✅ | Découpage par `RecursiveCharacterTextSplitter` |
| `processing/embeddings.py` | ✅ | Singleton EmbeddingModel — 384 dimensions |
| `storage/chroma_client.py` | ✅ | Upsert idempotent, distance cosinus |
| Intégration dans `consumer.py` | ✅ | Phase 1 + Phase 2 dans la même boucle |
| Upgrade modèle multilingue | ✅ | `paraphrase-multilingual-MiniLM-L12-v2` |
| `scripts/test_chroma_search.py` | ✅ | Recherche interactive validée (FR + EN) |

**Critère validé** : 100 chunks indexés (384 dims). Recherche EN → 63%+ de similarité.

---

### Phase 3 — Hybrid GraphRAG (L'Intelligence Structurelle) 🔄 EN COURS

**Objectif** : Dépasser la simple recherche vectorielle en construisant une connaissance structurée
du marché des talents sous forme de graphe de connaissances.

#### Decision architecturale : Pattern Microsoft GraphRAG

Notre Phase 3 adopte une architecture **Hybrid GraphRAG** inspirée des travaux de Microsoft Research
(Edge et al., 2024). Elle repose sur la séparation de deux flux complémentaires :

| Flux | Mode | Rôle |
|---|---|---|
| **Pipeline Vectoriel** (Phase 2) | Temps réel (streaming Kafka) | Recherche rapide par similarité sémantique — reste intact |
| **Batch Job GraphRAG** (Phase 3) | Asynchrone (déclenché manuellement) | Extraction de connaissance structurée depuis MongoDB |

#### Fonctionnement du Batch Job

```
MongoDB (CVs bruts)
    |
    v
[1] entity_extractor.py
    LLM (Groq llama3-70b) --> {entities: [...], relations: [...]}
    |
    v
[2] graph_builder.py
    NetworkX DiGraph (in-memory)
    Noeuds : candidats, competences, entreprises, secteurs
    Aretes : travaille_avec, possede_competence, experience_dans
    |
    v
[3] community_detector.py
    Algorithme Louvain/Leiden
    --> Communautes semantiques (ex: "cluster Data Science", "cluster Sante")
    |
    v
[4] community_summarizer.py
    LLM --> Resume textuel de chaque communaute
    |
    v
[5] ChromaDB (nouvelle collection : "community_summaries")
    Vecteurs des resumes -> recherche globale multi-CV
```

#### Pourquoi cette architecture ?

- **Recherche vectorielle seule** : bonne pour retrouver des chunks similaires
  mais aveugle aux relations entre profils (ex: "qui a travaillé avec des data engineers ?").
- **GraphRAG** : permet des requêtes globales (*"Quel est le profil type du cluster Data Science ?"*)
  impossibles avec une simple distance cosinus.
- **Hybride** : les deux modes coexistent — le retriever choisit la stratégie selon la requête.

#### Nouvelle collection ChromaDB

| Collection | Contenu | Usage |
|---|---|---|
| `cv_embeddings` | Chunks individuels des CVs (Phase 2) | Requêtes locales — profil par profil |
| `community_summaries` | Résumés LLM des communautés NetworkX | Requêtes globales — vue d'ensemble du marché |

| Sous-étape | Statut | Livrable |
|---|---|---|
| `generation/llm_client.py` — Client Groq | 🔄 | `generate_text()` + `extract_json()` |
| `graph/entity_extractor.py` — Extraction d'entités | ⬜ | JSON structuré entités/relations par CV |
| `graph/graph_builder.py` — Construction NetworkX | ⬜ | DiGraph peuplé depuis MongoDB |
| `graph/community_detector.py` — Détection communautés | ⬜ | Clusters sémantiques identifiés |
| `graph/community_summarizer.py` — Résumés LLM | ⬜ | Textes de synthèse par communauté |
| Indexation `community_summaries` dans ChromaDB | ⬜ | 2ème collection vectorielle opérationnelle |

**Critère de validation** : Requête globale (*"Décris le profil type d'un expert en cybersécurité"*)
retournant une synthèse LLM basée sur les résumés de communautés.

---

### Phase 4 — Interface B2B (Streamlit UI) ⬜ A VENIR

**Objectif** : Dashboard professionnel permettant la recherche en langage naturel.

| Sous-étape | Statut | Livrable |
|---|---|---|
| `interface/app.py` — Dashboard analytique | ⬜ | Champ de recherche, filtres, affichage résultats |
| `interface/components/result_card.py` — Result Cards | ⬜ | Carte profil HTML/CSS : score de matching, compétences clés, synthèse IA |
| Mini-chatbot par profil (optionnel) | ⬜ | Bouton par CV → chatbot contextuel exclusif au profil |

**Critère de validation** : Interface fluide, recherche de bout en bout fonctionnelle, résultats pertinents et bien mis en forme.

---

## 7. Dépendances Python (`requirements.txt`)

```
kafka-python        # Streaming Kafka (Producer / Consumer)
pymongo             # Client MongoDB
chromadb            # Base vectorielle in-process
sentence-transformers  # Génération d'embeddings (all-MiniLM-L6-v2)
torch               # Backend calcul tenseur (requis par sentence-transformers)
langchain           # Orchestration pipeline RAG
streamlit           # Interface utilisateur B2B
python-dotenv       # Chargement .env → config/settings.py
Faker               # Génération de CVs factices (scripts/ uniquement)
```

---

## 8. Commandes de Référence

```powershell
# Activer l'environnement virtuel (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Démarrer l'infrastructure Docker
docker compose up -d

# Vérifier les conteneurs
docker compose ps

# Lancer l'interface Streamlit
streamlit run interface/app.py

# Générer les CVs factices
python scripts/generate_fake_cvs.py

# Arrêter tous les conteneurs
docker compose down
```

---

*Dernière mise à jour : Phase 3 démarrée — Hybrid GraphRAG. `generation/llm_client.py` en cours.*
