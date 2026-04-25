"""
ingestion/producer.py
=====================
Kafka Producer — Lit les CVs JSON depuis data/sample_cvs/ et les publie
sur le topic Kafka défini dans config/settings.py.

Ce module est strictement découplé : il ne sait pas ce que fait le Consumer.
Sa seule responsabilité est de lire des fichiers et d'écrire dans Kafka.

Usage (depuis la racine du projet, .venv activé) :
    python ingestion/producer.py
"""

import json
import logging
import sys
import time
from pathlib import Path

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable, KafkaError

# --------------------------------------------------------------------------- #
#  Résolution du chemin racine — fonctionne quel que soit le CWD              #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC,
)

# --------------------------------------------------------------------------- #
#  Configuration du logger                                                     #
#  Format : [PRODUCER] 2026-04-14 00:41:00 — message                         #
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("PRODUCER")

# Dossier contenant les CVs JSON à envoyer
CV_DIR = PROJECT_ROOT / "data" / "sample_cvs"

# Délai entre chaque envoi (en secondes) — pour visualiser l'animation en test
SEND_DELAY = 0.5


# --------------------------------------------------------------------------- #
#  Sérialiseur JSON — encode le dict Python en bytes UTF-8 pour Kafka         #
# --------------------------------------------------------------------------- #
def json_serializer(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


# --------------------------------------------------------------------------- #
#  Création du Producer Kafka                                                  #
# --------------------------------------------------------------------------- #
def create_producer() -> KafkaProducer:
    """
    Instancie et retourne un KafkaProducer connecté au broker configuré.

    Returns:
        KafkaProducer: Instance prête à publier des messages.

    Raises:
        SystemExit: Si le broker est inaccessible au démarrage.
    """
    logger.info(f"[PRODUCER] Connexion au broker : {KAFKA_BOOTSTRAP_SERVERS}")
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=json_serializer,
            # Attendre l'accusé de réception d'au moins 1 broker avant de continuer
            acks=1,
            # Timeout de connexion initiale (ms)
            request_timeout_ms=10_000,
            # Nombre de tentatives en cas d'échec réseau transitoire
            retries=3,
        )
        logger.info("[PRODUCER] ✅ Connecté au broker Kafka.")
        return producer

    except NoBrokersAvailable:
        logger.error(
            "[PRODUCER] ❌ Aucun broker Kafka disponible.\n"
            "   → Vérifiez que vos conteneurs Docker sont bien démarrés :\n"
            "     docker compose ps"
        )
        sys.exit(1)


# --------------------------------------------------------------------------- #
#  Callback de confirmation d'envoi                                            #
# --------------------------------------------------------------------------- #
def on_send_success(record_metadata, cv_name: str) -> None:
    """Appelé par Kafka quand le message est bien reçu par le broker."""
    logger.info(
        f"[PRODUCER] ✅ Envoyé   : {cv_name:<40} "
        f"| topic={record_metadata.topic} "
        f"| partition={record_metadata.partition} "
        f"| offset={record_metadata.offset}"
    )


def on_send_error(exc, cv_name: str) -> None:
    """Appelé par Kafka si l'envoi d'un message échoue."""
    logger.error(f"[PRODUCER] ❌ Échec envoi : {cv_name} — {exc}")


# --------------------------------------------------------------------------- #
#  Fonction principale de publication                                          #
# --------------------------------------------------------------------------- #
def publish_cvs(producer: KafkaProducer) -> int:
    """
    Parcourt le dossier data/sample_cvs/, lit chaque fichier JSON,
    et publie son contenu sur le topic Kafka.

    Args:
        producer: Instance KafkaProducer active.

    Returns:
        int: Nombre de messages envoyés avec succès.
    """
    cv_files = sorted(CV_DIR.glob("*.json"))

    if not cv_files:
        logger.warning(
            f"[PRODUCER] ⚠️  Aucun fichier JSON trouvé dans : {CV_DIR}\n"
            "   → Exécutez d'abord : python scripts/prepare_kaggle_data.py"
        )
        return 0

    logger.info(f"[PRODUCER] 📂 {len(cv_files)} CV(s) trouvé(s) dans {CV_DIR}")
    logger.info(f"[PRODUCER] 📡 Publication sur le topic : '{KAFKA_TOPIC}'\n")

    sent_count = 0

    for cv_file in cv_files:
        # ── Lecture du fichier JSON ────────────────────────────────────────
        try:
            with open(cv_file, "r", encoding="utf-8") as f:
                cv_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[PRODUCER] ❌ Lecture impossible : {cv_file.name} — {e}")
            continue

        # Identifiant lisible pour les logs
        cv_label = f"{cv_data.get('name', '???')} - {cv_data.get('title', '???')}"

        # ── Envoi asynchrone avec callbacks ───────────────────────────────
        # La clé Kafka est l'ID du CV (bytes) — garantit que tous les messages
        # d'un même CV vont dans la même partition (cohérence de l'ordre)
        key = cv_data.get("id", cv_file.stem).encode("utf-8")

        producer.send(
            KAFKA_TOPIC,
            key=key,
            value=cv_data,
        ).add_callback(
            lambda meta, name=cv_label: on_send_success(meta, name)
        ).add_errback(
            lambda exc, name=cv_label: on_send_error(exc, name)
        )

        sent_count += 1

        # Pause volontaire pour visualiser le flux en temps réel lors des tests
        time.sleep(SEND_DELAY)

    return sent_count


# --------------------------------------------------------------------------- #
#  Point d'entrée                                                              #
# --------------------------------------------------------------------------- #
def main() -> None:
    logger.info("=" * 65)
    logger.info("  SmartRecruit AI — Kafka Producer")
    logger.info("=" * 65)

    producer = create_producer()

    try:
        sent = publish_cvs(producer)
    finally:
        # flush() attend que TOUS les messages en attente soient acquittés
        # avant de fermer la connexion — critique pour ne perdre aucun message
        logger.info("\n[PRODUCER] ⏳ Flush — attente des accusés de réception...")
        producer.flush()
        producer.close()
        logger.info(f"[PRODUCER] 🎉 Session terminée. {sent} message(s) publiés sur '{KAFKA_TOPIC}'.")


if __name__ == "__main__":
    main()
