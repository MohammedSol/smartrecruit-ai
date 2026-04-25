"""
ingestion/consumer.py
=====================
Kafka Consumer — Écoute le topic Kafka, désérialise les CV JSON,
et les persiste dans MongoDB via upsert (sans doublon).

Responsabilités STRICTEMENT limitées à la Phase 1 :
    ✅ Consommer les messages Kafka
    ✅ Sauvegarder le JSON brut dans MongoDB
    ❌ ChromaDB / Chunking / Embeddings → Phase 2

Couplage : Ce module est découplé du Producer.
Il ignore comment les messages ont été produits.

Usage (depuis la racine du projet, .venv activé) :
    python ingestion/consumer.py

Arrêt propre : Ctrl+C
"""

import json
import logging
import signal
import sys
from pathlib import Path

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable, KafkaError
from pymongo import MongoClient, UpdateOne
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

# --------------------------------------------------------------------------- #
#  Configuration du logger                                                     #
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("CONSUMER")

# Identifiant du groupe de consommateurs Kafka.
# Kafka mémorise l'offset de ce groupe → un redémarrage reprend là où il s'est arrêté.
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
    logger.info(f"[CONSUMER] Connexion à MongoDB : {MONGO_URI}")
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5_000)
        # Ping pour valider la connexion réelle avant de démarrer la boucle
        client.admin.command("ping")
        collection = client[MONGO_DB_NAME][MONGO_COLLECTION]
        logger.info(
            f"[CONSUMER] ✅ MongoDB connecté — "
            f"BDD: '{MONGO_DB_NAME}' | Collection: '{MONGO_COLLECTION}'"
        )
        return client, collection
    except ConnectionFailure as e:
        logger.error(
            f"[CONSUMER] ❌ Impossible de joindre MongoDB.\n"
            f"   → Vérifiez que le conteneur est bien démarré : docker compose ps\n"
            f"   Détail : {e}"
        )
        sys.exit(1)


# --------------------------------------------------------------------------- #
#  Connexion Kafka Consumer                                                    #
# --------------------------------------------------------------------------- #
def create_consumer() -> KafkaConsumer:
    """
    Instancie et retourne un KafkaConsumer prêt à consommer.

    Paramètres clés :
        - auto_offset_reset='earliest' : lit depuis le début du topic
          si ce groupe n'a jamais consommé (rattrape les messages en attente).
        - enable_auto_commit=True : valide automatiquement l'offset
          après chaque batch traité.
        - group_id : identifiant du groupe — Kafka retient la position
          de lecture entre deux démarrages du consumer.

    Returns:
        KafkaConsumer: Instance abonnée au topic.

    Raises:
        SystemExit: Si le broker est inaccessible.
    """
    logger.info(f"[CONSUMER] Connexion au broker : {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"[CONSUMER] Topic : '{KAFKA_TOPIC}' | Groupe : '{CONSUMER_GROUP_ID}'")
    try:
        consumer = KafkaConsumer(
            KAFKA_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            # Désérialise automatiquement les bytes JSON en dict Python
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
            # Lit depuis le début si ce groupe n'a pas encore d'offset enregistré
            auto_offset_reset="earliest",
            # Valide l'offset automatiquement (simplifie la gestion pour un PFA)
            enable_auto_commit=True,
            auto_commit_interval_ms=1_000,
            # Identifiant du groupe de consommateurs
            group_id=CONSUMER_GROUP_ID,
            # Timeout de connexion
            request_timeout_ms=15_000,
            # Délai max d'attente si le topic est vide (ms) — évite le busy-loop
            consumer_timeout_ms=-1,  # -1 = boucle infinie (pas de timeout)
        )
        logger.info(f"[CONSUMER] ✅ Abonné au topic '{KAFKA_TOPIC}'.")
        return consumer
    except NoBrokersAvailable:
        logger.error(
            "[CONSUMER] ❌ Aucun broker Kafka disponible.\n"
            "   → Vérifiez que vos conteneurs Docker sont bien démarrés :\n"
            "     docker compose ps"
        )
        sys.exit(1)


# --------------------------------------------------------------------------- #
#  Persistance MongoDB — Upsert                                               #
# --------------------------------------------------------------------------- #
def upsert_cv(collection, cv_data: dict) -> str:
    """
    Insère ou met à jour un CV dans MongoDB via upsert.

    Filtre sur le champ `id` du CV (UUID stable généré à l'ETL).
    → Si le CV n'existe pas : insertion.
    → Si le CV existe déjà : mise à jour du document (idempotent).
    Cette stratégie permet de relancer le pipeline sans créer de doublons.

    Args:
        collection: Collection MongoDB cible.
        cv_data:    Dictionnaire représentant le CV.

    Returns:
        str: 'inserted' | 'updated' selon l'opération effectuée.

    Raises:
        PyMongoError: Propagée si l'opération échoue.
    """
    result = collection.update_one(
        filter={"id": cv_data["id"]},    # Critère de recherche d'un doublon
        update={"$set": cv_data},         # Remplace/écrase tous les champs
        upsert=True,                       # Crée le document s'il n'existe pas
    )
    return "inserted" if result.upserted_id else "updated"


# --------------------------------------------------------------------------- #
#  Boucle principale de consommation                                           #
# --------------------------------------------------------------------------- #
def consume(consumer: KafkaConsumer, collection) -> None:
    """
    Boucle infinie d'écoute du topic Kafka.
    Chaque message reçu est désérialisé, loggué et persisté dans MongoDB.
    Arrêt propre via Ctrl+C (KeyboardInterrupt).

    Args:
        consumer:   Instance KafkaConsumer active.
        collection: Collection MongoDB cible.
    """
    logger.info("\n[CONSUMER] 👂 En écoute... (Ctrl+C pour arrêter proprement)\n")
    processed = 0

    for message in consumer:
        try:
            cv_data = message.value  # Déjà désérialisé par value_deserializer

            # Validation minimale : le champ 'id' est indispensable pour l'upsert
            if "id" not in cv_data:
                logger.warning(
                    f"[CONSUMER] ⚠️  Message ignoré (champ 'id' manquant) "
                    f"— offset={message.offset}"
                )
                continue

            # Persistance dans MongoDB
            operation = upsert_cv(collection, cv_data)

            cv_label = f"{cv_data.get('name', '???')} — {cv_data.get('title', '???')}"

            if operation == "inserted":
                logger.info(
                    f"[CONSUMER] 💾 CV sauvegardé dans MongoDB : {cv_label:<50} "
                    f"| offset={message.offset}"
                )
            else:
                logger.info(
                    f"[CONSUMER] 🔄 CV mis à jour dans MongoDB  : {cv_label:<50} "
                    f"| offset={message.offset}"
                )

            processed += 1

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(
                f"[CONSUMER] ❌ Message malformé ignoré — offset={message.offset} | {e}"
            )
        except PyMongoError as e:
            logger.error(
                f"[CONSUMER] ❌ Erreur MongoDB — offset={message.offset} | {e}"
            )
            # On continue la boucle — un échec ponctuel ne doit pas tuer le consumer


# --------------------------------------------------------------------------- #
#  Point d'entrée avec Graceful Shutdown                                       #
# --------------------------------------------------------------------------- #
def main() -> None:
    logger.info("=" * 65)
    logger.info("  SmartRecruit AI — Kafka Consumer")
    logger.info("=" * 65)

    mongo_client, collection = create_mongo_client()
    consumer = create_consumer()

    try:
        consume(consumer, collection)

    except KeyboardInterrupt:
        # Ctrl+C — arrêt demandé par l'utilisateur
        logger.info("\n[CONSUMER] 🛑 Arrêt demandé (Ctrl+C).")

    except KafkaError as e:
        logger.error(f"[CONSUMER] ❌ Erreur Kafka inattendue : {e}")

    finally:
        # Fermeture propre dans tous les cas (arrêt normal, exception, Ctrl+C)
        logger.info("[CONSUMER] ⏳ Fermeture des connexions...")
        try:
            consumer.close()
            logger.info("[CONSUMER] ✅ KafkaConsumer fermé.")
        except Exception as e:
            logger.warning(f"[CONSUMER] ⚠️  Erreur à la fermeture du consumer : {e}")

        try:
            mongo_client.close()
            logger.info("[CONSUMER] ✅ MongoClient fermé.")
        except Exception as e:
            logger.warning(f"[CONSUMER] ⚠️  Erreur à la fermeture de MongoDB : {e}")

        logger.info("[CONSUMER] 👋 Arrêt propre effectué.")


if __name__ == "__main__":
    main()
