"""
scripts/check_pii_fields.py
============================
Diagnostic PII — Vérifie la présence de champs email/phone dans MongoDB
avant d'implémenter le Sprint D (chiffrement AES/Fernet).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pymongo
from config.settings import MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION

SEP  = "─" * 60
BOLD = "═" * 60

def check():
    print(f"\n{BOLD}")
    print("  SmartRecruit AI — Diagnostic PII (pré-Sprint D)")
    print(BOLD)

    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    col = client[MONGO_DB_NAME][MONGO_COLLECTION]

    total = col.count_documents({})
    print(f"\n  Total CVs dans MongoDB : {total}")

    if total == 0:
        print("  [ERREUR] Collection vide.")
        return

    # -- Clés candidates pour email et téléphone
    email_keys = ["email", "Email", "mail", "e_mail", "contact_email"]
    phone_keys = ["phone", "Phone", "telephone", "tel", "mobile",
                  "phone_number", "contact", "numero", "portable"]

    print(f"\n{SEP}")
    print("  Recherche des champs EMAIL")
    print(SEP)
    email_key_found = None
    for k in email_keys:
        n = col.count_documents({k: {"$exists": True, "$ne": ""}})
        if n > 0:
            print(f"  ✅ Clé '{k}' trouvée → {n}/{total} documents")
            email_key_found = k
        else:
            n_exist = col.count_documents({k: {"$exists": True}})
            if n_exist > 0:
                print(f"  ⚠️  Clé '{k}' existe mais vide → {n_exist}/{total} documents")

    if not email_key_found:
        print("  ❌ Aucun champ email trouvé")

    print(f"\n{SEP}")
    print("  Recherche des champs TÉLÉPHONE")
    print(SEP)
    phone_key_found = None
    for k in phone_keys:
        n = col.count_documents({k: {"$exists": True, "$ne": ""}})
        if n > 0:
            print(f"  ✅ Clé '{k}' trouvée → {n}/{total} documents")
            phone_key_found = k
        else:
            n_exist = col.count_documents({k: {"$exists": True}})
            if n_exist > 0:
                print(f"  ⚠️  Clé '{k}' existe mais vide → {n_exist}/{total} documents")

    if not phone_key_found:
        print("  ❌ Aucun champ téléphone trouvé")

    # -- Afficher les clés réelles d'un document exemple
    print(f"\n{SEP}")
    print("  Structure réelle d'un document (exemple)")
    print(SEP)
    sample = col.find_one({}, {"_id": 0})
    if sample:
        print(f"  Clés disponibles : {list(sample.keys())}")
        print()
        for k in list(sample.keys())[:12]:
            val = str(sample.get(k, ""))[:60]
            print(f"  {k:<20} : {val}")

    # -- Conclusion
    print(f"\n{BOLD}")
    print("  CONCLUSION")
    print(BOLD)

    if email_key_found or phone_key_found:
        print(f"\n  ✅ Données PII présentes — Sprint D peut s'appliquer directement.")
        if email_key_found:
            print(f"     → Chiffrer le champ : '{email_key_found}'")
        if phone_key_found:
            print(f"     → Chiffrer le champ : '{phone_key_found}'")
    else:
        print("\n  ⚠️  Aucune PII (email/phone) trouvée dans les documents.")
        print("     Deux options :")
        print("     1. Injecter des emails/phones de démonstration (script de patch)")
        print("     2. Chiffrer un autre champ sensible présent (ex: 'location', 'name')")
        print("        pour démontrer le principe devant le jury")

    print(f"\n{BOLD}\n")


if __name__ == "__main__":
    check()
