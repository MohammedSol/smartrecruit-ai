"""
scripts/audit_chroma.py
=======================
Script d'investigation READ-ONLY de la base vectorielle ChromaDB.

Objectif : Diagnostiquer l'état réel de la collection sans AUCUNE modification.
           Permet notamment de détecter un conflit de dimension de vecteur
           (ex: collection initialisée avec dim=3 lors du dummy test,
           alors que le pipeline réel produit des vecteurs dim=384).

CONTRAINTES STRICTES :
    - AUCUN import de embeddings.py, chunking.py, ou consumer.py.
    - AUCUN appel à add(), upsert(), delete(), ou reset().
    - Uniquement : get(), count(), list_collections() — méthodes READ-ONLY.

Usage :
    python -m scripts.audit_chroma

Rapport attendu :
    - Nombre d'éléments dans la collection
    - Dimension du premier vecteur stocké
    - Contenu du premier document et ses métadonnées
"""

import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
#  Résolution du chemin racine                                                 #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import chromadb
from chromadb.config import Settings

from config.settings import CHROMA_PERSIST_DIR, CHROMA_COLLECTION


# --------------------------------------------------------------------------- #
#  Helpers d'affichage                                                         #
# --------------------------------------------------------------------------- #
SEP   = "-" * 65
BOLD  = "=" * 65


def section(title: str) -> None:
    print(f"\n  {SEP}")
    print(f"  {title}")
    print(f"  {SEP}")


# --------------------------------------------------------------------------- #
#  Audit principal                                                             #
# --------------------------------------------------------------------------- #
def audit() -> None:
    print(f"\n{BOLD}")
    print("  SmartRecruit AI - Audit ChromaDB  (READ-ONLY)")
    print(BOLD)

    # ── 1. Connexion READ-ONLY au PersistentClient ───────────────────────────
    persist_path = Path(CHROMA_PERSIST_DIR)

    section("1. Connexion a ChromaDB")
    print(f"  Dossier de persistance : {persist_path.resolve()}")
    print(f"  Dossier existe         : {persist_path.exists()}")

    if not persist_path.exists():
        print(
            "\n  [!] ERREUR : Le dossier ChromaDB n'existe pas.\n"
            "      Le pipeline consumer.py n'a peut-etre jamais ete lance.\n"
            "      Commande pour initialiser : python ingestion/consumer.py"
        )
        return

    try:
        client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=Settings(anonymized_telemetry=False),
        )
        print("  Connexion : OK")
    except Exception as e:
        print(f"\n  [!] ECHEC de connexion au PersistentClient.\n  Detail : {e}")
        return

    # ── 2. Liste de toutes les collections ──────────────────────────────────
    section("2. Collections presentes dans la base")
    try:
        all_collections = client.list_collections()
        if not all_collections:
            print("  Aucune collection trouvee — base vide.")
        else:
            for col in all_collections:
                print(f"  - Nom : '{col.name}'")
    except Exception as e:
        print(f"  [!] Impossible de lister les collections : {e}")
        return

    # ── 3. Ouverture de la collection cible ─────────────────────────────────
    section(f"3. Collection cible : '{CHROMA_COLLECTION}'")
    try:
        # get_collection() (sans get_or_create) — lecture seule, ne crée rien
        collection = client.get_collection(name=CHROMA_COLLECTION)
        print(f"  Collection trouvee : OK")
    except Exception as e:
        print(
            f"  [!] ERREUR : Impossible d'ouvrir la collection '{CHROMA_COLLECTION}'.\n"
            f"  Detail : {e}\n\n"
            f"  Cause probable : la collection n'a jamais ete creee.\n"
            f"  Solution       : lancer le pipeline consumer.py au moins une fois."
        )
        return

    # ── 4. Compte total d'éléments ───────────────────────────────────────────
    section("4. Nombre d'elements indexes")
    try:
        total = collection.count()
        print(f"  collection.count() = {total}")
        if total == 0:
            print(
                "\n  [!] AVERTISSEMENT : La collection est VIDE.\n"
                "      Aucun chunk n'a encore ete indexe.\n"
                "      Cause probable : le consumer.py (Phase 2) n'a pas encore tourne,\n"
                "      ou une erreur s'est produite lors de l'indexation."
            )
            return
    except Exception as e:
        print(f"  [!] Erreur lors du count() : {e}")
        return

    # ── 5. Lecture du premier élément ────────────────────────────────────────
    section("5. Premier element stocke (get limit=1)")
    try:
        result = collection.get(
            limit=1,
            include=["embeddings", "documents", "metadatas"],
        )
    except Exception as e:
        print(f"  [!] Erreur lors de collection.get() : {e}")
        return

    # ── IDs ─────────────────────────────────────────────────────────────────
    ids = result.get("ids", [])
    if not ids:
        print("  [!] Aucun element retourne par get() — collection peut-etre corrompue.")
        return

    print(f"  chunk_id   : {ids[0]}")

    # ── Dimension du vecteur ─────────────────────────────────────────────────
    embeddings = result.get("embeddings")
    section("6. Dimension du vecteur (POINT CRITIQUE)")
    if embeddings is not None and len(embeddings) > 0 and embeddings[0] is not None:
        dim = len(embeddings[0])
        print(f"  len(embeddings[0]) = {dim}")

        if dim == 384:
            print(
                "  DIAGNOSTIC : OK — Dimension correcte pour all-MiniLM-L6-v2.\n"
                "               Le pipeline Phase 2 a produit les bons vecteurs."
            )
        elif dim == 3:
            print(
                "  DIAGNOSTIC : CONFLIT DETECTE !\n"
                "  La collection a ete initialisee avec des vecteurs FACTICES (dim=3)\n"
                "  lors du test dummy (python -m storage.chroma_client).\n\n"
                "  ChromaDB a verrouille la dimension a 3 pour cette collection.\n"
                "  Le pipeline reel produit des vecteurs dim=384 -> INCOMPATIBLE.\n\n"
                "  >>> SOLUTION : Supprimer le dossier chroma_data/ et relancer.\n"
                "  >>> Commande PowerShell :\n"
                "      Remove-Item -Recurse -Force chroma_data\n"
                "      python ingestion/producer.py   (dans terminal 2)\n"
                "      python ingestion/consumer.py   (dans terminal 1)"
            )
        else:
            print(
                f"  DIAGNOSTIC : Dimension inattendue ({dim}).\n"
                f"               Attendu : 384 (all-MiniLM-L6-v2).\n"
                f"               Verifiez le modele d'embedding utilise."
            )
    else:
        print("  [!] Aucun vecteur retourne (embeddings=None ou vide).")
        print("      La collection stocke peut-etre des documents sans embeddings.")

    # ── Document ─────────────────────────────────────────────────────────────
    section("7. Contenu du document")
    documents = result.get("documents", [])
    if documents and documents[0]:
        print(f"  Texte : \"{documents[0][:200]}{'...' if len(documents[0]) > 200 else ''}\"")
    else:
        print("  [!] Aucun document texte stocke.")

    # ── Métadonnées ──────────────────────────────────────────────────────────
    section("8. Metadonnees associees")
    metadatas = result.get("metadatas", [])
    if metadatas and metadatas[0]:
        for key, value in metadatas[0].items():
            print(f"  {key:<15} : {value}")
    else:
        print("  [!] Aucune metadonnee stockee.")

    # ── Récapitulatif ────────────────────────────────────────────────────────
    section("RECAPITULATIF DU DIAGNOSTIC")
    dim_str = str(len(embeddings[0])) if (embeddings is not None and len(embeddings) > 0 and embeddings[0] is not None) else "N/A"
    print(f"  Collection          : {CHROMA_COLLECTION}")
    print(f"  Elements indexes    : {total}")
    print(f"  Dimension vecteurs  : {dim_str}")
    print(f"  Dossier persistance : {persist_path.resolve()}")
    print(f"\n{BOLD}\n")


# --------------------------------------------------------------------------- #
#  Point d'entrée                                                              #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    audit()
