"""
scripts/encrypt_pii_mongodb.py
================================
Sprint D — Chiffre les champs email et phone existants dans MongoDB.

Ce script est IDEMPOTENT :
    - Si un champ est déjà chiffré (commence par "gAAAAAB"), il est ignoré.
    - Relancer le script plusieurs fois ne re-chiffre pas les données.

Usage :
    python scripts/encrypt_pii_mongodb.py

Prérequis :
    FERNET_KEY doit être définie dans le fichier .env
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import pymongo
from config.settings import MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION
from security.encryption import encrypt, is_encrypted, _load_key

SEP  = "─" * 60
BOLD = "═" * 60

PII_FIELDS = ["email", "phone"]   # Champs à chiffrer


def run():
    print(f"\n{BOLD}")
    print("  SmartRecruit AI — Chiffrement PII MongoDB (Sprint D)")
    print(BOLD)

    # Vérification de la clé
    key = _load_key()
    if not key:
        print("\n  [ERREUR] FERNET_KEY absente du .env")
        print("  Générez-en une :")
        print("  python -c \"from cryptography.fernet import Fernet; print('FERNET_KEY=' + Fernet.generate_key().decode())\"")
        sys.exit(1)

    print(f"\n  Clé Fernet chargée : {key[:20].decode()}...")

    # Connexion MongoDB
    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    col    = client[MONGO_DB_NAME][MONGO_COLLECTION]
    total  = col.count_documents({})
    print(f"  Documents MongoDB  : {total}")

    if total == 0:
        print("  [ERREUR] Collection vide.")
        sys.exit(0)

    print(f"\n{SEP}")
    print("  Chiffrement en cours...")
    print(SEP)

    chiffres     = {f: 0 for f in PII_FIELDS}
    deja_chiffres = {f: 0 for f in PII_FIELDS}
    vides        = {f: 0 for f in PII_FIELDS}

    for cv in col.find({}, {"_id": 1, **{f: 1 for f in PII_FIELDS}}):
        doc_id  = cv["_id"]
        updates = {}

        for field in PII_FIELDS:
            valeur = str(cv.get(field, "")).strip()

            if not valeur or valeur.lower() in ("n/a", "non renseigné", ""):
                vides[field] += 1
                continue

            if is_encrypted(valeur):
                deja_chiffres[field] += 1
                continue

            # Chiffrement
            updates[field] = encrypt(valeur, key)
            chiffres[field] += 1

        if updates:
            col.update_one({"_id": doc_id}, {"$set": updates})

    # Rapport
    print(f"\n{BOLD}")
    print("  RAPPORT DE CHIFFREMENT")
    print(BOLD)
    for field in PII_FIELDS:
        print(f"\n  [{field}]")
        print(f"    Nouvellement chiffrés : {chiffres[field]}")
        print(f"    Déjà chiffrés (skip)  : {deja_chiffres[field]}")
        print(f"    Vides/N/A (skip)      : {vides[field]}")

    # Vérification visuelle — 3 exemples
    print(f"\n{SEP}")
    print("  Vérification — 3 exemples dans MongoDB (valeurs chiffrées)")
    print(SEP)
    for cv in col.find({}, {"_id": 0, "name": 1, "email": 1, "phone": 1}).limit(3):
        email_val = cv.get("email", "N/A")
        print(f"  {cv['name']:<25} | {email_val[:45]}...")

    print(f"\n{BOLD}")
    print("  ✅ Chiffrement terminé — ouvrez MongoDB Compass pour confirmer.")
    print("  Les emails afficheront 'gAAAAAB...' (illisibles sans la clé).")
    print(BOLD + "\n")


if __name__ == "__main__":
    run()
