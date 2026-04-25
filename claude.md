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
| **Modèle d'embedding** | `all-MiniLM-L6-v2` | Via `sentence-transformers`. Vecteurs de 384 dimensions. Bon équilibre vitesse/qualité. |
| **Orchestration RAG** | `LangChain` | Gère le pipeline Retrieve → Augment → Generate. Connecteurs ChromaDB, MongoDB et Groq. |
| **LLM Provider** | **API Groq** | Gratuit en tier libre, très rapide. Modèles : `llama3-8b-8192` ou `mixtral-8x7b-32768`. Clé dans `.env` (`GROQ_API_KEY`). |
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
│   ├── sample_cvs/             ← CVs JSON générés par Faker (tests)
│   └── generated/              ← Données intermédiaires (NON versionné)
│
├── ingestion/
│   ├── __init__.py
│   ├── producer.py             ← Lit les CVs JSON → publie sur Kafka topic
│   └── consumer.py             ← Consomme Kafka → stocke Mongo → vectorise ChromaDB
│
├── processing/
│   ├── __init__.py
│   ├── chunking.py             ← Découpe un CV JSON en sections textuelles
│   └── embeddings.py           ← Génère les vecteurs via sentence-transformers
│
├── rag/
│   ├── __init__.py
│   ├── retriever.py            ← Cherche dans ChromaDB → récupère dans Mongo
│   ├── chain.py                ← Pipeline LangChain (Retriever → Prompt → Groq)
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
│       └── result_card.py      ← Carte profil HTML/CSS (score, skills, synthèse IA)
│
├── scripts/
│   └── generate_fake_cvs.py    ← Génère 50-100 CVs JSON avec Faker
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
EMBEDDING_MODEL=all-MiniLM-L6-v2

# --- LLM (Groq) ---
LLM_PROVIDER=groq
LLM_MODEL=llama3-8b-8192
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

### Phase 0 — Fondations & Données Factices ✅ VALIDÉE

| Sous-étape | Statut | Livrable |
|---|---|---|
| Arborescence complète du projet | ✅ | Tous les dossiers et fichiers vides créés |
| `docker-compose.yml` (Kafka KRaft + MongoDB) | ✅ | 2 conteneurs `Healthy` sur `smartrecruit-net` |
| Environnement Python 3.11 + `.venv` | ✅ | 9 packages installés, venv Windows natif |
| `config/settings.py` | ✅ | Chargement centralisé validé |
| `scripts/generate_fake_cvs.py` | ⏳ | 50-100 CVs JSON dans `data/sample_cvs/` |

**Critère de sortie Phase 0** : Les fichiers JSON générés sont lisibles et conformes au schéma canonique (R4).

---

### Phase 1 — Pipeline de Données (Ingestion) ⬜ À VENIR

**Objectif** : Faire circuler un CV JSON de son fichier source jusqu'à MongoDB, via Kafka.

| Sous-étape | Statut | Livrable |
|---|---|---|
| `scripts/prepare_kaggle_data.py` — ETL CSV → JSON | ⬜ | CVs nettoyés et normalisés |
| `ingestion/producer.py` — Kafka Producer | ⬜ | Publie les CVs JSON sur le topic `cv-ingestion` |
| `ingestion/consumer.py` — Kafka Consumer | ⬜ | Consomme et persiste les CVs dans MongoDB |

**Critère de validation** : 2 terminaux en parallèle (Producer + Consumer). Vérification visuelle des documents dans MongoDB Compass.

---

### Phase 2 — Vectorisation (Moteur de Recherche) ⬜ À VENIR

**Objectif** : Transformer chaque CV en vecteurs sémantiques indexés dans ChromaDB.

| Sous-étape | Statut | Livrable |
|---|---|---|
| `processing/chunking.py` — Découpage sémantique | ⬜ | CV découpé en sections (expérience, formation, compétences) |
| `processing/embeddings.py` — Vectorisation | ⬜ | Vecteurs 384 dimensions via `all-MiniLM-L6-v2` |
| `storage/chroma_client.py` — Indexation | ⬜ | Chunks + métadonnées stockés dans ChromaDB |
| Intégration dans `consumer.py` | ⬜ | Après insert Mongo → chunking → embedding → ChromaDB |

**Critère de validation** : Script terminal effectuant une requête et retournant le **Top 3 des chunks** les plus proches via distance Cosinus.

---

### Phase 3 — Moteur RAG (L'Intelligence) ⬜ À VENIR

**Objectif** : Connecter la recherche sémantique à un LLM (Groq) via LangChain.

| Sous-étape | Statut | Livrable |
|---|---|---|
| `rag/retriever.py` — Retriever hybride | ⬜ | Cherche IDs dans ChromaDB → tire profils complets de MongoDB |
| `rag/prompts.py` — Templates de prompts | ⬜ | Prompts structurés pour l'analyse de profils recrutement |
| `rag/chain.py` — Pipeline LangChain + Groq | ⬜ | Chaîne Retriever → Prompt → LLM → Réponse |

**Critère de validation** : Script Q&A terminal — requête complexe (ex: *"Trouve un data engineer avec Spark et 3 ans d'expérience"*) → réponse LLM cohérente, sourcée, et citant les profils trouvés.

---

### Phase 4 — Interface B2B (Streamlit UI) ⬜ À VENIR

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

*Dernière mise à jour : Phase 0 complète. Prochaine étape : `scripts/generate_fake_cvs.py`.*
