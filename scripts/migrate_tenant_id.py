"""
scripts/migrate_tenant_id.py
==============================
Script de migration Sprint B — Tagging Multi-Tenant des documents ChromaDB.

PROBLEME :
    Les CVs existants dans ChromaDB ont ete indexes SANS la metadonnee
    `tenant_id`. Le filtre multi-tenant du Sprint B retourne donc 0 resultats.

SOLUTION :
    Ce script lit tous les documents de la collection `cv_embeddings`,
    et les met a jour en ajoutant {"tenant_id": "entreprise_A"} dans
    leurs metadonnees via collection.update().

IMPORTANT :
    - Ce script est IDEMPOTENT : on peut le relancer plusieurs fois sans risque.
    - Il ne touche PAS aux vecteurs (embeddings) — uniquement les metadonnees.
    - Il ne touche PAS a la collection `community_insights`.

Usage :
    python scripts/migrate_tenant_id.py

Duree estimee : < 5 secondes pour 50-100 CVs.
"""

import sys
from pathlib import Path

# Resolution du chemin racine du projet
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import chromadb
from config.settings import CHROMA_PERSIST_DIR, CHROMA_COLLECTION

# Tenant a appliquer a tous les CVs existants
DEFAULT_TENANT = "entreprise_A"


def migrate():
    print("=" * 60)
    print("  SmartRecruit AI — Migration Multi-Tenant (Sprint B)")
    print("=" * 60)

    # 1. Connexion a ChromaDB
    print(f"\n  Connexion a ChromaDB : {CHROMA_PERSIST_DIR}")
    client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))

    # 2. Recuperation de la collection cv_embeddings
    try:
        collection = client.get_collection(CHROMA_COLLECTION)
    except Exception as e:
        print(f"\n  [ERREUR] Collection '{CHROMA_COLLECTION}' introuvable : {e}")
        print("  Verifiez que ChromaDB est peuple (python scripts/run_graph_batch.py)")
        sys.exit(1)

    # 3. Recuperation de tous les documents (sans les embeddings pour la rapidite)
    print(f"  Collection cible : '{CHROMA_COLLECTION}'")
    result = collection.get(include=["metadatas"])

    ids       = result["ids"]
    metadatas = result["metadatas"]
    total     = len(ids)

    if total == 0:
        print("\n  [ATTENTION] Aucun document trouve dans la collection.")
        print("  Lancez d'abord le pipeline d'ingestion.")
        sys.exit(0)

    print(f"  Documents trouves : {total}")

    # 4. Identification des documents a migrer (sans tenant_id)
    a_migrer = [
        (doc_id, meta)
        for doc_id, meta in zip(ids, metadatas)
        if meta.get("tenant_id") != DEFAULT_TENANT
    ]

    deja_tagges = total - len(a_migrer)
    print(f"  Deja tagges       : {deja_tagges}")
    print(f"  A migrer          : {len(a_migrer)}")

    if not a_migrer:
        print(f"\n  Tous les documents ont deja le tenant_id='{DEFAULT_TENANT}'.")
        print("  Aucune migration necessaire.")
        print("\n" + "=" * 60)
        print("  Migration terminee — 0 document modifie.")
        print("=" * 60 + "\n")
        return

    # 5. Mise a jour par batch (ChromaDB supporte .update() sur les metadonnees)
    print(f"\n  Mise a jour en cours...")
    ids_batch      = []
    metadatas_batch = []

    for doc_id, meta in a_migrer:
        # On conserve toutes les metadonnees existantes et on ajoute tenant_id
        nouvelle_meta = {**meta, "tenant_id": DEFAULT_TENANT}
        ids_batch.append(doc_id)
        metadatas_batch.append(nouvelle_meta)

    # Appel unique pour tous les documents (plus efficace qu'un appel par doc)
    collection.update(ids=ids_batch, metadatas=metadatas_batch)

    print(f"  {len(ids_batch)} documents mis a jour avec tenant_id='{DEFAULT_TENANT}'")

    # 6. Verification post-migration
    print("\n  Verification post-migration...")
    verification = collection.get(
        include=["metadatas"],
        where={"tenant_id": DEFAULT_TENANT}
    )
    verifies = len(verification["ids"])

    print(f"  Documents avec tenant_id='{DEFAULT_TENANT}' : {verifies}/{total}")

    if verifies == total:
        print(f"\n  ✅ Migration reussie — {verifies}/{total} documents tagges.")
    else:
        manquants = total - verifies
        print(f"\n  ⚠️  {manquants} documents n'ont pas ete migres.")
        print("  Relancez ce script pour les traiter.")

    print("\n" + "=" * 60)
    print(f"  Migration terminee.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    migrate()
