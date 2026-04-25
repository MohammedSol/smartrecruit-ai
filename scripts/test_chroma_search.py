"""
scripts/test_chroma_search.py
=============================
Test interactif de la recherche semantique — Etape 2.5.

Ce script valide que le moteur vectoriel ChromaDB repond correctement
a des requetes en langage naturel (francais ou anglais).

Flux :
    Texte utilisateur --> EmbeddingModel --> vecteur float[384]
                      --> collection.query() --> Top-3 chunks
                      --> Affichage : score, mongo_id, extrait

Prerequis :
    Le consumer.py (Phase 1 + Phase 2) doit avoir ete execute au moins une fois.
    Verifier avec : python -m scripts.audit_chroma

Usage :
    python -m scripts.test_chroma_search
"""

import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
#  Chemin racine                                                               #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import chromadb
from chromadb.config import Settings

from config.settings import CHROMA_PERSIST_DIR, CHROMA_COLLECTION
from processing.embeddings import EmbeddingModel


# --------------------------------------------------------------------------- #
#  Constantes                                                                  #
# --------------------------------------------------------------------------- #
N_RESULTS   = 3
EXTRACT_LEN = 150
SEP_THIN    = "-" * 65
SEP_BOLD    = "=" * 65


# --------------------------------------------------------------------------- #
#  Initialisation (une seule fois avant la boucle)                             #
# --------------------------------------------------------------------------- #
def init() -> tuple:
    """
    Charge le modele d'embedding et ouvre la collection ChromaDB.

    Returns:
        tuple: (EmbeddingModel, Collection chromadb)

    Raises:
        SystemExit: Si la connexion ChromaDB echoue ou si la collection est introuvable.
    """
    print(f"\n{SEP_BOLD}")
    print("  SmartRecruit AI - Moteur de Recherche Semantique")
    print("  Etape 2.5 : Test interactif ChromaDB")
    print(SEP_BOLD)

    # Modele d'embedding
    print("\n  [1/2] Chargement du modele d'embedding (all-MiniLM-L6-v2)...")
    embedder = EmbeddingModel()
    print(f"        Modele pret. Dimension : {embedder.get_dimension()}")

    # Connexion ChromaDB
    print("\n  [2/2] Connexion a ChromaDB...")
    persist_path = Path(CHROMA_PERSIST_DIR)

    if not persist_path.exists():
        print(
            "\n  [ERREUR] Dossier ChromaDB introuvable : {persist_path}\n"
            "  Executez d'abord le pipeline :\n"
            "    python ingestion/producer.py   (terminal 2)\n"
            "    python ingestion/consumer.py   (terminal 1)"
        )
        sys.exit(1)

    try:
        client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=Settings(anonymized_telemetry=False),
        )
        collection = client.get_collection(name=CHROMA_COLLECTION)
    except Exception as e:
        print(f"\n  [ERREUR] Connexion ChromaDB : {e}")
        sys.exit(1)

    total = collection.count()
    print(f"        Collection '{CHROMA_COLLECTION}' — {total} chunk(s) indexes.")

    if total == 0:
        print(
            "\n  [AVERTISSEMENT] La base est vide — aucune recherche possible.\n"
            "  Executez le pipeline consumer.py + producer.py d'abord."
        )
        sys.exit(1)

    print(f"\n  {SEP_THIN}")
    print("  Requetes acceptees en francais ou en anglais.")
    print("  Commandes : 'q' | 'quit' pour quitter   |   Ctrl+C pour interrompre")
    print(f"  {SEP_THIN}\n")

    return embedder, collection


# --------------------------------------------------------------------------- #
#  Affichage d'un resultat                                                     #
# --------------------------------------------------------------------------- #
def display_result(rank: int, hit_id: str, hit_doc: str, hit_meta: dict, hit_dist: float) -> None:
    """Affiche un resultat de recherche formate en ASCII pur."""
    # Distance cosinus [0,2] -> similarite [0,1]
    # ChromaDB retourne une distance cosinus normalisee : 0 = identique, 1 = orthogonal
    similarity = round(1.0 - hit_dist, 4)

    cv_name    = hit_meta.get("cv_name",    "Inconnu")
    cv_title   = hit_meta.get("cv_title",   "N/A")
    mongo_id   = hit_meta.get("mongo_id",   "N/A")
    chunk_idx  = hit_meta.get("chunk_index", "?")
    extrait    = hit_doc[:EXTRACT_LEN] + ("..." if len(hit_doc) > EXTRACT_LEN else "")
    distance   = round(hit_dist, 4)

    print(f"  #{rank}  {cv_name}  |  {cv_title}")
    print(f"       Similarite : {similarity:.1%}   (distance cosinus : {distance})")
    print(f"       mongo_id   : {mongo_id}")
    print(f"       Chunk #{chunk_idx}   : \"{extrait}\"")
    print(f"  {SEP_THIN}")


# --------------------------------------------------------------------------- #
#  Execution d'une recherche                                                   #
# --------------------------------------------------------------------------- #
def search(query: str, embedder: EmbeddingModel, collection) -> None:
    """
    Vectorise la requete et interroge ChromaDB.

    Args:
        query:      Texte saisi par l'utilisateur.
        embedder:   Modele d'embedding (Singleton).
        collection: Collection ChromaDB ouverte.
    """
    if not query.strip():
        print("  [!] Requete vide — saisissez au moins un mot.\n")
        return

    print(f"\n  Recherche : \"{query}\"")
    print(f"  {SEP_THIN}")

    # Vectorisation de la requete avec le meme modele que le pipeline
    try:
        query_vector = embedder.get_embedding(query)
    except Exception as e:
        print(f"  [ERREUR] Vectorisation impossible : {e}\n")
        return

    # Requete ChromaDB
    try:
        # n_results limite automatiquement au nombre d'elements disponibles
        effective_n = min(N_RESULTS, collection.count())
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=effective_n,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        print(f"  [ERREUR] Recherche ChromaDB : {e}\n")
        return

    ids       = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not ids:
        print("  Aucun resultat trouve.\n")
        return

    print(f"\n  Top {len(ids)} resultats pour : \"{query}\"\n")
    print(f"  {SEP_THIN}")

    for rank, (hit_id, doc, meta, dist) in enumerate(
        zip(ids, documents, metadatas, distances), start=1
    ):
        display_result(rank, hit_id, doc, meta, dist)

    print()


# --------------------------------------------------------------------------- #
#  Boucle interactive principale                                               #
# --------------------------------------------------------------------------- #
def main() -> None:
    embedder, collection = init()

    while True:
        try:
            query = input("  > Recherche : ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  Arret. Au revoir !")
            break

        if query.lower() in ("q", "quit", "exit"):
            print("\n  Au revoir !")
            break

        search(query, embedder, collection)


if __name__ == "__main__":
    main()
