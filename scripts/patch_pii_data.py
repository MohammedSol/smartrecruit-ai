"""
scripts/patch_pii_data.py
==========================
Génère des données PII réalistes (email + phone) pour les 50 CVs MongoDB.

POURQUOI :
    Les CVs ont des valeurs placeholder ("non-renseigné@example.com", "N/A").
    Pour démontrer le chiffrement AES (Sprint D) de manière convaincante devant
    le jury, on a besoin de PII qui ressemblent à de vraies données.

CE QUE LE SCRIPT FAIT :
    Pour chaque candidat, il génère :
    - Email : prenom.nom@domaine.com (domaine varié selon un hash du nom)
    - Phone : +33 6 XX XX XX XX (format français réaliste)

    Le script est IDEMPOTENT : il ne modifie que les CVs avec des valeurs vides.

Usage :
    python scripts/patch_pii_data.py
"""

import sys
import random
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pymongo
from config.settings import MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION

SEP  = "─" * 60
BOLD = "═" * 60

# Domaines emails variés pour la démo
DOMAINS = [
    "gmail.com", "outlook.fr", "yahoo.fr", "protonmail.com",
    "hotmail.com", "icloud.com", "laposte.net", "free.fr"
]

PLACEHOLDER_EMAILS = {"non-renseigné@example.com", "non-renseigne@example.com", "", "n/a"}
PLACEHOLDER_PHONES = {"n/a", "", "non spécifié", "non renseigné"}


def normalize(text: str) -> str:
    """Supprime les accents et met en minuscules."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def generate_email(name: str, seed: int) -> str:
    """Génère un email réaliste depuis un nom complet."""
    parts = name.strip().split()
    if len(parts) >= 2:
        prenom = normalize(parts[0])
        nom    = normalize(parts[-1])
        local  = f"{prenom}.{nom}"
    else:
        local = normalize(name.replace(" ", "."))

    # Domaine déterministe basé sur le seed (pas aléatoire → reproductible)
    domain = DOMAINS[seed % len(DOMAINS)]
    return f"{local}@{domain}"


def generate_phone(seed: int) -> str:
    """Génère un numéro de téléphone français réaliste."""
    rng = random.Random(seed)
    prefix = rng.choice(["06", "07"])
    digits = "".join([str(rng.randint(0, 9)) for _ in range(8)])
    # Format : +33 6 XX XX XX XX
    d = digits
    return f"+33 {prefix[1]} {d[0:2]} {d[2:4]} {d[4:6]} {d[6:8]}"


def patch():
    print(f"\n{BOLD}")
    print("  SmartRecruit AI — Patch PII pour Sprint D")
    print(BOLD)

    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    col = client[MONGO_DB_NAME][MONGO_COLLECTION]

    total = col.count_documents({})
    print(f"\n  Total CVs : {total}")
    print(f"\n{SEP}")

    patched_email = 0
    patched_phone = 0
    skipped       = 0

    for idx, cv in enumerate(col.find({}, {"_id": 1, "name": 1, "email": 1, "phone": 1})):
        doc_id = cv["_id"]
        name   = cv.get("name", f"Candidat_{idx}")
        email  = str(cv.get("email", "")).strip().lower()
        phone  = str(cv.get("phone", "")).strip().lower()

        updates = {}

        # Patch email si placeholder
        if email in PLACEHOLDER_EMAILS or not email:
            updates["email"] = generate_email(name, idx)
            patched_email += 1

        # Patch phone si placeholder
        if phone in PLACEHOLDER_PHONES or not phone:
            updates["phone"] = generate_phone(idx)
            patched_phone += 1

        if updates:
            col.update_one({"_id": doc_id}, {"$set": updates})
            print(f"  [{idx+1:02d}] {name:<25} → email: {updates.get('email', 'inchangé')}")
        else:
            skipped += 1

    print(f"\n{SEP}")
    print(f"\n  Emails patchés  : {patched_email}/{total}")
    print(f"  Phones patchés  : {patched_phone}/{total}")
    print(f"  Déjà renseignés : {skipped}")

    # Vérification
    print(f"\n{SEP}")
    print("  Vérification — 3 exemples après patch")
    print(SEP)
    for cv in col.find({}, {"_id": 0, "name": 1, "email": 1, "phone": 1}).limit(3):
        print(f"  {cv['name']:<25} | {cv['email']:<35} | {cv['phone']}")

    print(f"\n{BOLD}")
    print("  ✅ Patch terminé — données PII prêtes pour le Sprint D")
    print(BOLD + "\n")


if __name__ == "__main__":
    patch()
