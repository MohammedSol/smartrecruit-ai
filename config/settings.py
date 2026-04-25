"""
config/settings.py
==================
Point d'entrée UNIQUE pour toutes les variables de configuration de SmartRecruit AI.
Aucun autre module ne doit appeler os.getenv() ou lire le .env directement.
Aucun mot de passe ne doit être codé en dur dans ce fichier.

Usage dans n'importe quel module du projet :
    from config.settings import KAFKA_BOOTSTRAP_SERVERS, MONGO_URI, ...
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
#  Chargement du fichier .env                                                  #
#  Cherche .env à la racine du projet (deux niveaux au-dessus de ce fichier)  #
# --------------------------------------------------------------------------- #
_ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_ROOT_DIR / ".env")


# --------------------------------------------------------------------------- #
#  BLOC 1 — Kafka                                                              #
# --------------------------------------------------------------------------- #

# Adresse du broker Kafka (variable .env : KAFKA_BROKER_URL)
KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BROKER_URL", "localhost:9092")

# Topic sur lequel les CV JSON sont publiés / consommés
KAFKA_TOPIC: str = os.getenv("KAFKA_TOPIC_CV", "cv_ingestion")


# --------------------------------------------------------------------------- #
#  BLOC 2 — MongoDB                                                            #
# --------------------------------------------------------------------------- #

# URI de connexion complète — construite dans le .env, jamais ici
MONGO_URI: str = os.getenv("MONGO_URI", "")

# Nom de la base de données
MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "smartrecruit")

# Nom de la collection qui stocke les CV complets
MONGO_COLLECTION: str = os.getenv("MONGO_COLLECTION_NAME", "cvs")


# --------------------------------------------------------------------------- #
#  BLOC 3 — ChromaDB                                                           #
# --------------------------------------------------------------------------- #

# Dossier de persistance locale des vecteurs (créé automatiquement si absent)
CHROMA_PERSIST_DIR: str = os.getenv(
    "CHROMA_PERSIST_DIR",
    str(_ROOT_DIR / "chroma_data"),
)

# Nom de la collection vectorielle dans ChromaDB
CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "cv_embeddings")


# --------------------------------------------------------------------------- #
#  BLOC 4 — Modèle d'embedding (sentence-transformers)                        #
# --------------------------------------------------------------------------- #

# all-MiniLM-L6-v2 : bon équilibre vitesse / qualité (384 dimensions)
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


# --------------------------------------------------------------------------- #
#  BLOC 5 — LLM (API Groq — décision validée Phase 3)                        #
# --------------------------------------------------------------------------- #

# Fournisseur LLM : "groq" | "openai" | "ollama"
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")

# Modèle Groq : "llama3-8b-8192" | "mixtral-8x7b-32768"
LLM_MODEL: str = os.getenv("LLM_MODEL", "llama3-8b-8192")

# Clé API Groq (obligatoire en Phase 3)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")


# --------------------------------------------------------------------------- #
#  BLOC 6 — Streamlit                                                          #
# --------------------------------------------------------------------------- #

# Port sur lequel l'interface recruteur est exposée
STREAMLIT_PORT: int = int(os.getenv("STREAMLIT_PORT", "8501"))


# --------------------------------------------------------------------------- #
#  Validation au démarrage                                                     #
#  Lève une EnvironmentError explicite si une variable critique est absente    #
# --------------------------------------------------------------------------- #
_REQUIRED = {
    "KAFKA_BROKER_URL  → KAFKA_BOOTSTRAP_SERVERS": KAFKA_BOOTSTRAP_SERVERS,
    "KAFKA_TOPIC_CV    → KAFKA_TOPIC":            KAFKA_TOPIC,
    "MONGO_URI":                                   MONGO_URI,
    "MONGO_DB_NAME":                               MONGO_DB_NAME,
    "MONGO_COLLECTION_NAME → MONGO_COLLECTION":   MONGO_COLLECTION,
    "CHROMA_PERSIST_DIR":                          CHROMA_PERSIST_DIR,
    "CHROMA_COLLECTION":                           CHROMA_COLLECTION,
    "EMBEDDING_MODEL":                             EMBEDDING_MODEL,
}

_missing = [k for k, v in _REQUIRED.items() if not v]
if _missing:
    raise EnvironmentError(
        f"[settings.py] Variables d'environnement manquantes : {', '.join(_missing)}\n"
        f"Vérifiez votre fichier .env à la racine du projet."
    )
