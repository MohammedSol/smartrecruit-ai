"""
storage/chroma_client.py
========================
Gestionnaire de la base vectorielle ChromaDB pour SmartRecruit AI.

Rôle dans le pipeline :
    chunks + embeddings ──► ChromaManager.add_chunks() ──► chroma_data/ (disque)
    requête utilisateur + embedding ──► ChromaManager.query() ──► top-K chunks

Architecture :
    - PersistentClient   : stockage sur disque (dossier CHROMA_PERSIST_DIR).
                           Les données survivent aux redémarrages du processus.
    - Embedding externe  : on injecte nos propres vecteurs (all-MiniLM-L6-v2).
                           ChromaDB est utilisé comme index vectoriel pur.
    - Upsert             : l'insertion est idempotente — relancer le pipeline
                           ne crée pas de doublons (filtre sur chunk_id).
    - Lien MongoDB       : chaque chunk stocke {"mongo_id": "..."} en métadonnée
                           pour retrouver le document complet dans MongoDB.

Dépendance :
    pip install chromadb
    (chromadb == version dans requirements.txt)

Usage :
    from storage.chroma_client import ChromaManager
    manager = ChromaManager()
    manager.add_chunks(ids, chunks, embeddings, metadatas)
"""

import logging
import sys
from pathlib import Path

import chromadb
from chromadb.config import Settings

# --------------------------------------------------------------------------- #
#  Résolution du chemin racine (pour les exécutions directes et en module)    #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import CHROMA_COLLECTION, CHROMA_PERSIST_DIR

# --------------------------------------------------------------------------- #
#  Logger                                                                      #
# --------------------------------------------------------------------------- #
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Classe ChromaManager                                                        #
# --------------------------------------------------------------------------- #
class ChromaManager:
    """
    Gestionnaire de la base vectorielle ChromaDB.

    Responsabilités :
        - Connexion au PersistentClient ChromaDB (dossier CHROMA_PERSIST_DIR)
        - Création ou récupération de la collection vectorielle (CHROMA_COLLECTION)
        - Insertion idempotente des chunks + embeddings + métadonnées
        - Recherche de similarité (query) par vecteur — utilisée par le RAG

    Attributs publics :
        collection : Collection ChromaDB active

    Example :
        >>> manager = ChromaManager()
        >>> manager.add_chunks(
        ...     chunk_ids=["cv1_chunk0"],
        ...     chunks=["Python developer with 5 years experience"],
        ...     embeddings=[[0.1, 0.2, ...]],
        ...     metadatas=[{"mongo_id": "abc123", "cv_name": "Alice"}]
        ... )
        >>> print(manager.collection.count())
        1
    """

    def __init__(self) -> None:
        """
        Initialise le client ChromaDB et la collection.

        Crée le dossier CHROMA_PERSIST_DIR si inexistant.
        La collection est créée si absente, ou récupérée si elle existe déjà
        (get_or_create_collection — idempotent).

        Raises:
            RuntimeError: Si la connexion à ChromaDB échoue.
        """
        persist_path = Path(CHROMA_PERSIST_DIR)
        persist_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"[CHROMA] Connexion au PersistentClient : {persist_path}")

        try:
            # PersistentClient stocke les données sur disque dans persist_path.
            # Settings(anonymized_telemetry=False) désactive l'envoi de télémétrie
            # à Chroma HQ — bonne pratique en environnement académique / PFA.
            self._client = chromadb.PersistentClient(
                path=str(persist_path),
                settings=Settings(anonymized_telemetry=False),
            )

            # get_or_create_collection :
            #   - Si la collection "cv_embeddings" n'existe pas → la crée
            #   - Si elle existe déjà (redémarrage) → la récupère telle quelle
            # embedding_function=None : on fournit nos propres vecteurs pré-calculés.
            # ChromaDB n'essaiera donc pas d'en calculer lui-même.
            self.collection = self._client.get_or_create_collection(
                name=CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"},  # Distance cosinus pour la similarité sémantique
            )

            logger.info(
                f"[CHROMA] Collection '{CHROMA_COLLECTION}' prête. "
                f"Documents indexés : {self.collection.count()}"
            )

        except Exception as e:
            logger.error(f"[CHROMA] Echec de l'initialisation : {e}")
            raise RuntimeError(
                f"Impossible d'initialiser ChromaDB dans '{persist_path}'. Cause : {e}"
            ) from e

    # ── Insertion ────────────────────────────────────────────────────────────

    def add_chunks(
        self,
        chunk_ids:  list[str],
        chunks:     list[str],
        embeddings: list[list[float]],
        metadatas:  list[dict],
    ) -> None:
        """
        Insère (ou met à jour) des chunks dans la collection ChromaDB.

        Méthode utilisée : `upsert` (update + insert).
            → Si un chunk_id existe déjà : mise à jour du vecteur et des métadonnées.
            → Si un chunk_id est nouveau : insertion.
        Cela rend le pipeline entièrement idempotent : relancer n'est jamais destructeur.

        Convention de nommage des IDs :
            Les chunk_ids doivent être stables et uniques, ex :
            "{cv_id}_chunk_{index}" → "a3f8b2c1_chunk_0", "a3f8b2c1_chunk_1", ...

        Args:
            chunk_ids:  Identifiants uniques et stables pour chaque chunk.
            chunks:     Textes bruts des chunks (stockés comme "documents" dans Chroma).
            embeddings: Vecteurs pré-calculés par EmbeddingModel (dimension 384).
            metadatas:  Métadonnées par chunk. Doit contenir au minimum "mongo_id"
                        pour faire le lien avec le document MongoDB original.

        Raises:
            ValueError: Si les listes n'ont pas toutes la même longueur.
            RuntimeError: Si l'upsert échoue côté ChromaDB.

        Example:
            >>> manager.add_chunks(
            ...     chunk_ids  = ["cv1_chunk_0", "cv1_chunk_1"],
            ...     chunks     = ["Python expert...", "Managed a team of 5..."],
            ...     embeddings = [[0.12, -0.03, ...], [0.45, 0.01, ...]],
            ...     metadatas  = [{"mongo_id": "abc"}, {"mongo_id": "abc"}]
            ... )
        """
        # Validation de cohérence
        lengths = {len(chunk_ids), len(chunks), len(embeddings), len(metadatas)}
        if len(lengths) != 1:
            raise ValueError(
                f"[CHROMA] Toutes les listes doivent avoir la même longueur. "
                f"Recu : ids={len(chunk_ids)}, chunks={len(chunks)}, "
                f"embeddings={len(embeddings)}, metadatas={len(metadatas)}"
            )

        if not chunk_ids:
            logger.debug("[CHROMA] add_chunks() appelé avec une liste vide — ignoré.")
            return

        try:
            self.collection.upsert(
                ids=chunk_ids,
                documents=chunks,       # Textes bruts (utiles pour le debug et la restitution)
                embeddings=embeddings,  # Vecteurs pré-calculés (float[384])
                metadatas=metadatas,    # {"mongo_id": "...", "cv_name": "...", ...}
            )
            logger.info(
                f"[CHROMA] {len(chunk_ids)} chunk(s) inseres/mis a jour. "
                f"Total dans la collection : {self.collection.count()}"
            )
        except Exception as e:
            logger.error(f"[CHROMA] Echec de l'upsert : {e}")
            raise RuntimeError(f"Erreur lors de l'insertion dans ChromaDB : {e}") from e

    # ── Recherche sémantique ─────────────────────────────────────────────────

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 5,
    ) -> list[dict]:
        """
        Recherche les n_results chunks les plus similaires au vecteur de requête.

        Utilisé par le module RAG (Phase 3) pour retrouver les CVs pertinents.

        Args:
            query_embedding: Vecteur de la requête (même dimension que les chunks).
            n_results:       Nombre de résultats à retourner (défaut : 5).

        Returns:
            list[dict]: Liste de résultats, chacun contenant :
                {
                    "id"        : chunk_id,
                    "document"  : texte du chunk,
                    "metadata"  : dict (inclut mongo_id),
                    "distance"  : score de distance cosinus (0 = identique)
                }

        Raises:
            RuntimeError: Si la requête échoue.
        """
        count = self.collection.count()
        if count == 0:
            logger.warning("[CHROMA] La collection est vide — aucun résultat possible.")
            return []

        # Limiter n_results au nombre de documents disponibles
        effective_n = min(n_results, count)

        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=effective_n,
                include=["documents", "metadatas", "distances"],
            )

            # Reformater en liste de dicts lisibles
            hits = []
            for i in range(len(results["ids"][0])):
                hits.append({
                    "id":       results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                })
            return hits

        except Exception as e:
            logger.error(f"[CHROMA] Echec de la requête : {e}")
            raise RuntimeError(f"Erreur lors de la recherche dans ChromaDB : {e}") from e

    def count(self) -> int:
        """Retourne le nombre de chunks actuellement indexés."""
        return self.collection.count()

    def reset_collection(self) -> None:
        """
        Supprime et recrée la collection (utile pour les tests ou un re-indexage complet).

        ⚠️ DESTRUCTIF — toutes les données indexées sont perdues.
        """
        logger.warning(f"[CHROMA] Suppression de la collection '{CHROMA_COLLECTION}'...")
        self._client.delete_collection(CHROMA_COLLECTION)
        self.collection = self._client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        logger.warning("[CHROMA] Collection réinitialisée (vide).")


# --------------------------------------------------------------------------- #
#  Test standalone (dummy test — pas de vrais embeddings)                     #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    print("=" * 65)
    print("  Test — storage/chroma_client.py  (dummy vectors dim=3)")
    print("=" * 65)

    # ── Initialisation ───────────────────────────────────────────────────────
    print("\n[TEST 1] Connexion et création de collection...")
    manager = ChromaManager()
    print(f"  Collection '{CHROMA_COLLECTION}' — documents avant insertion : {manager.count()}")

    # Nettoyer pour repartir d'un état propre à chaque exécution du test
    manager.reset_collection()
    print(f"  Apres reset : {manager.count()} document(s)")

    # ── Insertion de 2 faux chunks ───────────────────────────────────────────
    print("\n[TEST 2] Insertion de 2 chunks factices (vecteurs dim=3)...")

    # NOTE : en production les vecteurs sont de dimension 384 (all-MiniLM-L6-v2).
    # Ici on utilise dim=3 pour la lisibilité du test — ChromaDB accepte n'importe quelle dim.
    fake_ids        = ["test_cv_001_chunk_0", "test_cv_001_chunk_1"]
    fake_chunks     = [
        "Experienced Python developer with expertise in machine learning.",
        "Managed a team of 5 engineers delivering a real-time data pipeline.",
    ]
    fake_embeddings = [
        [0.10, 0.85, 0.32],   # Vecteur fictif chunk 0
        [0.77, 0.21, 0.54],   # Vecteur fictif chunk 1
    ]
    fake_metadatas  = [
        {"mongo_id": "507f1f77bcf86cd799439011", "cv_name": "Alice Dupont", "chunk_index": 0},
        {"mongo_id": "507f1f77bcf86cd799439011", "cv_name": "Alice Dupont", "chunk_index": 1},
    ]

    manager.add_chunks(fake_ids, fake_chunks, fake_embeddings, fake_metadatas)

    count_after = manager.count()
    print(f"  Documents dans la collection apres insertion : {count_after}")
    assert count_after == 2, f"ECHEC : attendu 2, obtenu {count_after}"
    print("  OK — 2 chunks indexes")

    # ── Test idempotence (upsert) ────────────────────────────────────────────
    print("\n[TEST 3] Idempotence — reinsertion des memes IDs...")
    manager.add_chunks(fake_ids, fake_chunks, fake_embeddings, fake_metadatas)
    count_after_upsert = manager.count()
    assert count_after_upsert == 2, f"ECHEC : l'upsert a cree des doublons ({count_after_upsert})"
    print(f"  Apres upsert : {count_after_upsert} document(s) (pas de doublons)")
    print("  OK — Idempotence confirmee")

    # ── Test query ───────────────────────────────────────────────────────────
    print("\n[TEST 4] Recherche semantique par vecteur...")
    query_vec = [0.12, 0.80, 0.30]  # Proche du chunk 0
    hits = manager.query(query_embedding=query_vec, n_results=2)
    print(f"  {len(hits)} résultat(s) retourné(s) :")
    for hit in hits:
        print(f"    ID       : {hit['id']}")
        print(f"    Document : {hit['document'][:60]}...")
        print(f"    mongo_id : {hit['metadata']['mongo_id']}")
        print(f"    Distance : {hit['distance']:.4f}")
        print()

    print("[OK] chroma_client.py valide. Pret pour le pipeline Phase 2.")
