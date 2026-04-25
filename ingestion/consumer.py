"""
ingestion/consumer.py
=====================
Kafka Consumer — Pipeline complet Phase 1 + Phase 2.

Flux de traitement pour chaque message Kafka (CV JSON) :
    ┌─────────────────────────────────────────────────────────────┐
    │  1. Réception du message Kafka (JSON désérialisé)           │
    │  2. [PHASE 1] Upsert du CV complet dans MongoDB             │
    │  3. [PHASE 2] Chunking du texte du CV                       │
    │  4. [PHASE 2] Vectorisation des chunks (EmbeddingModel)     │
    │  5. [PHASE 2] Indexation dans ChromaDB avec mongo_id        │
    └─────────────────────────────────────────────────────────────┘

Robustesse :
    - Si MongoDB échoue → le consumer s'arrête (erreur critique).
    - Si ChromaDB échoue → l'erreur est loggée, mais MongoDB n'est pas
      affecté et la boucle continue (tolérance aux pannes Phase 2).

Usage (depuis la racine du projet, .venv activé) :
    python ingestion/consumer.py

Arrêt propre : Ctrl+C
"""

import json
import logging
import sys
from pathlib import Path

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable, KafkaError
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError

# --------------------------------------------------------------------------- #
#  Résolution du chemin racine                                                 #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC,
    MONGO_URI,
    MONGO_DB_NAME,
    MONGO_COLLECTION,
)
from processing.chunking import chunk_cv
from processing.embeddings import EmbeddingModel
from storage.chroma_client import ChromaManager

# --------------------------------------------------------------------------- #
#  Configuration du logger                                                     #
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("CONSUMER")

CONSUMER_GROUP_ID = "smartrecruit-consumer-group"


# --------------------------------------------------------------------------- #
#  Connexion MongoDB                                                           #
# --------------------------------------------------------------------------- #
def create_mongo_client():
    """
    Crée et valide la connexion MongoDB.

    Returns:
        tuple: (MongoClient, Collection) prêts à l'emploi.

    Raises:
        SystemExit: Si MongoDB est inaccessible.
    """
    logger.info(f"[MONGO] Connexion : {MONGO_URI}")
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5_000)
        client.admin.command("ping")
        collection = client[MONGO_DB_NAME][MONGO_COLLECTION]
        logger.info(
            f"[MONGO] Connecte — BDD: '{MONGO_DB_NAME}' | Collection: '{MONGO_COLLECTION}'"
        )
        return client, collection
    except ConnectionFailure as e:
        logger.error(
            f"[MONGO] Impossible de joindre MongoDB.\n"
            f"   Verifiez : docker compose ps\n"
            f"   Detail   : {e}"
        )
        sys.exit(1)


# --------------------------------------------------------------------------- #
#  Connexion Kafka Consumer                                                    #
# --------------------------------------------------------------------------- #
def create_consumer() -> KafkaConsumer:
    """
    Instancie et retourne un KafkaConsumer prêt à consommer.

    Returns:
        KafkaConsumer: Instance abonnée au topic.

    Raises:
        SystemExit: Si le broker est inaccessible.
    """
    logger.info(f"[KAFKA] Connexion broker : {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"[KAFKA] Topic : '{KAFKA_TOPIC}' | Groupe : '{CONSUMER_GROUP_ID}'")
    try:
        consumer = KafkaConsumer(
            KAFKA_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            auto_commit_interval_ms=1_000,
            group_id=CONSUMER_GROUP_ID,
            request_timeout_ms=15_000,
            consumer_timeout_ms=-1,
        )
        logger.info(f"[KAFKA] Abonne au topic '{KAFKA_TOPIC}'.")
        return consumer
    except NoBrokersAvailable:
        logger.error(
            "[KAFKA] Aucun broker disponible.\n"
            "   Verifiez : docker compose ps"
        )
        sys.exit(1)


# --------------------------------------------------------------------------- #
#  PHASE 1 — Persistance MongoDB                                               #
# --------------------------------------------------------------------------- #
def upsert_cv(collection, cv_data: dict) -> tuple[str, str]:
    """
    Insère ou met à jour un CV dans MongoDB via upsert.

    Args:
        collection: Collection MongoDB cible.
        cv_data:    Dictionnaire CV au format canonique.

    Returns:
        tuple: (operation, mongo_id)
            operation : 'inserted' | 'updated'
            mongo_id  : str(ObjectId) du document dans MongoDB — utilisé
                        comme lien dans les métadonnées ChromaDB.

    Raises:
        PyMongoError: Propagée si l'opération échoue.
    """
    result = collection.update_one(
        filter={"id": cv_data["id"]},
        update={"$set": cv_data},
        upsert=True,
    )
    if result.upserted_id:
        # Nouveau document — l'ObjectId est retourné directement
        mongo_id = str(result.upserted_id)
        return "inserted", mongo_id
    else:
        # Document mis à jour — on relit l'ObjectId existant
        doc = collection.find_one({"id": cv_data["id"]}, {"_id": 1})
        mongo_id = str(doc["_id"]) if doc else cv_data["id"]
        return "updated", mongo_id


# --------------------------------------------------------------------------- #
#  PHASE 2 — Vectorisation & Indexation ChromaDB                              #
# --------------------------------------------------------------------------- #
def index_cv_in_chroma(
    cv_data:  dict,
    mongo_id: str,
    embedder: EmbeddingModel,
    chroma:   ChromaManager,
) -> int:
    """
    Découpe le CV en chunks, les vectorise et les indexe dans ChromaDB.

    Lien MongoDB ↔ ChromaDB :
        Chaque chunk stocke {"mongo_id": mongo_id} dans ses métadonnées.
        Le module RAG pourra ainsi retrouver le document complet dans Mongo
        à partir d'un résultat ChromaDB.

    Robustesse :
        Si le chunking ou l'embedding échoue pour un CV, on log l'erreur
        et on retourne 0 — la boucle principale continue normalement.

    Args:
        cv_data:  Dictionnaire CV complet.
        mongo_id: ObjectId MongoDB du CV (str).
        embedder: Instance Singleton EmbeddingModel.
        chroma:   Instance ChromaManager.

    Returns:
        int: Nombre de chunks indexés (0 si échec ou texte vide).
    """
    cv_id   = cv_data.get("id", mongo_id)
    cv_name = cv_data.get("name", "Inconnu")

    # ── 1. Chunking ─────────────────────────────────────────────────────────
    chunks = chunk_cv(cv_data)
    if not chunks:
        logger.debug(f"[CHROMA] Aucun chunk genere pour '{cv_name}' — CV ignoré pour l'indexation.")
        return 0

    # ── 2. Génération des IDs stables ────────────────────────────────────────
    # Format : "{cv_id}_chunk_{index}" → ex: "a3f8b2_chunk_0"
    # Stable entre les runs → upsert idempotent dans ChromaDB
    chunk_ids = [f"{cv_id}_chunk_{i}" for i in range(len(chunks))]

    # ── 3. Métadonnées (une par chunk) ───────────────────────────────────────
    metadatas = [
        {
            "mongo_id":    mongo_id,                        # Lien vers MongoDB
            "cv_id":       cv_id,                           # UUID du CV (schéma canonique)
            "cv_name":     cv_name,                         # Nom du candidat
            "cv_title":    cv_data.get("title", ""),        # Intitulé du poste
            "chunk_index": i,                               # Position du chunk dans le CV
        }
        for i in range(len(chunks))
    ]

    # ── 4. Vectorisation batch (optimisée) ───────────────────────────────────
    embeddings = embedder.get_embeddings(chunks)
    if len(embeddings) != len(chunks):
        logger.error(
            f"[CHROMA] Mismatch embeddings/chunks pour '{cv_name}' "
            f"({len(embeddings)} vs {len(chunks)}) — indexation annulee."
        )
        return 0

    # ── 5. Upsert dans ChromaDB ──────────────────────────────────────────────
    chroma.add_chunks(
        chunk_ids=chunk_ids,
        chunks=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    logger.info(
        f"[CHROMA] {len(chunks)} chunk(s) indexes pour : {cv_name} ({cv_id[:8]}...) "
        f"| mongo_id={mongo_id[:8]}..."
    )
    return len(chunks)


# --------------------------------------------------------------------------- #
#  Boucle principale de consommation                                           #
# --------------------------------------------------------------------------- #
def consume(
    consumer: KafkaConsumer,
    collection,
    embedder: EmbeddingModel,
    chroma:   ChromaManager,
) -> None:
    """
    Boucle infinie d'écoute du topic Kafka.
    Pour chaque message :
        1. Upsert MongoDB (Phase 1)
        2. Indexation ChromaDB (Phase 2) — dégradée si échec, sans impact Phase 1

    Args:
        consumer:   Instance KafkaConsumer active.
        collection: Collection MongoDB cible.
        embedder:   Modèle d'embedding (Singleton).
        chroma:     Gestionnaire ChromaDB.
    """
    logger.info("\n[CONSUMER] En ecoute... (Ctrl+C pour arreter proprement)\n")
    stats = {"processed": 0, "mongo_ok": 0, "chroma_ok": 0, "chroma_chunks": 0}

    for message in consumer:
        try:
            cv_data = message.value

            # Validation minimale
            if "id" not in cv_data:
                logger.warning(
                    f"[CONSUMER] Message ignore (champ 'id' manquant) — offset={message.offset}"
                )
                continue

            cv_label = f"{cv_data.get('name', '?')} — {cv_data.get('title', '?')}"

            # ── PHASE 1 : MongoDB ────────────────────────────────────────────
            try:
                operation, mongo_id = upsert_cv(collection, cv_data)
                icon = "OK" if operation == "inserted" else "MAJ"
                logger.info(
                    f"[MONGO]  [{icon}] {cv_label:<50} | offset={message.offset}"
                )
                stats["mongo_ok"] += 1
            except PyMongoError as e:
                logger.error(f"[MONGO]  Erreur pour '{cv_label}' : {e}")
                # Erreur MongoDB → on skippe aussi la Phase 2 (pas de mongo_id fiable)
                continue

            # ── PHASE 2 : ChromaDB ───────────────────────────────────────────
            # Isolée dans un try/except séparé : une erreur Chroma ne doit JAMAIS
            # impacter ni MongoDB ni la continuité de la boucle.
            try:
                n_chunks = index_cv_in_chroma(cv_data, mongo_id, embedder, chroma)
                if n_chunks > 0:
                    stats["chroma_ok"] += 1
                    stats["chroma_chunks"] += n_chunks
            except Exception as e:
                logger.error(
                    f"[CHROMA] Erreur d'indexation pour '{cv_label}' — "
                    f"MongoDB non affecte. Detail : {e}"
                )

            stats["processed"] += 1

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"[CONSUMER] Message malformé — offset={message.offset} | {e}")


# --------------------------------------------------------------------------- #
#  Point d'entrée avec Graceful Shutdown                                       #
# --------------------------------------------------------------------------- #
def main() -> None:
    logger.info("=" * 65)
    logger.info("  SmartRecruit AI — Kafka Consumer  (Phase 1 + Phase 2)")
    logger.info("=" * 65)

    # ── Connexions ───────────────────────────────────────────────────────────
    mongo_client, collection = create_mongo_client()
    consumer                 = create_consumer()

    # ── Phase 2 : chargement du modèle d'embedding et de ChromaDB ───────────
    # Le modèle est chargé UNE SEULE FOIS ici (Singleton) avant la boucle.
    # Cela évite de recharger ~80 Mo à chaque message.
    logger.info("[PHASE 2] Chargement du modele d'embedding...")
    embedder = EmbeddingModel()
    logger.info("[PHASE 2] Connexion a ChromaDB...")
    chroma = ChromaManager()
    logger.info(
        f"[PHASE 2] Pret. ChromaDB : {chroma.count()} chunk(s) deja indexes."
    )

    try:
        consume(consumer, collection, embedder, chroma)

    except KeyboardInterrupt:
        logger.info("\n[CONSUMER] Arret demande (Ctrl+C).")

    except KafkaError as e:
        logger.error(f"[CONSUMER] Erreur Kafka inattendue : {e}")

    finally:
        logger.info("[CONSUMER] Fermeture des connexions...")
        try:
            consumer.close()
            logger.info("[CONSUMER] KafkaConsumer ferme.")
        except Exception as e:
            logger.warning(f"[CONSUMER] Erreur fermeture consumer : {e}")

        try:
            mongo_client.close()
            logger.info("[CONSUMER] MongoClient ferme.")
        except Exception as e:
            logger.warning(f"[CONSUMER] Erreur fermeture MongoDB : {e}")

        logger.info("[CONSUMER] Arret propre effectue.")


if __name__ == "__main__":
    main()
