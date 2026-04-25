"""
processing/embeddings.py
========================
Module de vectorisation (Embedding) des chunks de CV.

Rôle dans le pipeline :
    chunk (str) ──► EmbeddingModel.get_embedding() ──► vecteur float[384]
    Les vecteurs sont ensuite indexés dans ChromaDB pour la recherche sémantique.

Modèle choisi : all-MiniLM-L6-v2
    - Dimension de sortie : 384 (compact et rapide)
    - Entraînement       : contrastive learning sur 1B+ paires de phrases
    - Cas d'usage        : sémantique, similarité, recherche d'information
    - Taille             : ~80 Mo (téléchargement unique via Hugging Face)
    - Inférence CPU      : ~20ms par phrase — viable sans GPU

Pattern Singleton :
    Le modèle SentenceTransformer prend ~2 secondes à charger en mémoire.
    Le Singleton garantit qu'il n'est chargé QU'UNE SEULE FOIS, quelle que
    soit la fréquence des appels dans le pipeline (producer, consumer, RAG...).

Dépendance :
    pip install sentence-transformers
    (déjà dans requirements.txt)
"""

import logging
from typing import Optional

from sentence_transformers import SentenceTransformer

from config.settings import EMBEDDING_MODEL

# --------------------------------------------------------------------------- #
#  Logger du module                                                            #
# --------------------------------------------------------------------------- #
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Classe singleton EmbeddingModel                                             #
# --------------------------------------------------------------------------- #
class EmbeddingModel:
    """
    Wrapper Singleton autour de SentenceTransformer.

    Garantit que le modèle all-MiniLM-L6-v2 n'est chargé qu'une seule fois
    en mémoire, même si EmbeddingModel() est instancié plusieurs milliers de fois.

    Pattern utilisé : Singleton via attribut de classe `_instance`.

    Usage :
        model = EmbeddingModel()
        vector = model.get_embedding("Python developer with 5 years experience")
        # vector → liste de 384 floats

    Note :
        SentenceTransformer télécharge automatiquement le modèle depuis
        Hugging Face au premier appel (~80 Mo), puis le cache localement dans
        ~/.cache/huggingface/. Les appels suivants sont instantanés.
    """

    # ── Attributs de classe partagés entre toutes les instances ─────────────
    _instance: Optional["EmbeddingModel"] = None   # Référence unique au singleton
    _model: Optional[SentenceTransformer] = None   # Modèle partagé en mémoire

    def __new__(cls) -> "EmbeddingModel":
        """
        Implémentation du Singleton.
        __new__ est appelé AVANT __init__. Si une instance existe déjà,
        on la retourne directement sans créer de nouvel objet.
        """
        if cls._instance is None:
            logger.info(
                f"[EMBEDDING] Première instanciation — chargement du modèle '{EMBEDDING_MODEL}'..."
            )
            cls._instance = super().__new__(cls)
            cls._model = cls._instance._load_model()
        return cls._instance

    def _load_model(self) -> SentenceTransformer:
        """
        Charge le modèle SentenceTransformer depuis le cache local ou Hugging Face.

        Returns:
            SentenceTransformer: Modèle prêt à l'inférence.

        Raises:
            RuntimeError: Si le modèle ne peut pas être chargé.
        """
        try:
            model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info(
                f"[EMBEDDING] Modèle '{EMBEDDING_MODEL}' charge en memoire. "
                f"Dimension de sortie : {model.get_sentence_embedding_dimension()}"
            )
            return model
        except Exception as e:
            logger.error(f"[EMBEDDING] Impossible de charger le modele : {e}")
            raise RuntimeError(
                f"Echec du chargement du modele d'embedding '{EMBEDDING_MODEL}'. "
                f"Verifiez votre connexion (1er telechargement) ou votre .env. Cause : {e}"
            ) from e

    # ── API publique ─────────────────────────────────────────────────────────

    def get_embedding(self, text: str) -> list[float]:
        """
        Vectorise un seul texte.

        Cas limite : si le texte est vide ou non-string, retourne un vecteur nul
        (liste de 0.0 de la bonne dimension) pour ne pas briser le pipeline.

        Args:
            text: Chunk de texte à vectoriser.

        Returns:
            list[float]: Vecteur de dimension 384.

        Example:
            >>> model = EmbeddingModel()
            >>> vector = model.get_embedding("Machine Learning Engineer")
            >>> len(vector)
            384
        """
        if not text or not isinstance(text, str):
            logger.warning("[EMBEDDING] Texte invalide recu — retourne vecteur nul")
            dim = self._model.get_sentence_embedding_dimension()
            return [0.0] * dim

        # encode() retourne un numpy.ndarray — .tolist() le convertit en list[float]
        vector = self._model.encode(text, convert_to_numpy=True)
        return vector.tolist()

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Vectorise un lot de textes de manière optimisée (batch processing).

        Avantage par rapport à N appels get_embedding() :
            SentenceTransformer parallélise les calculs en interne sur le lot entier.
            Sur CPU, un batch de 32 est ~5x plus rapide que 32 appels séquentiels.

        Args:
            texts: Liste de chunks à vectoriser (peut être vide).

        Returns:
            list[list[float]]: Liste de vecteurs, un par texte. Retourne []
                               si texts est vide ou invalide.

        Example:
            >>> model = EmbeddingModel()
            >>> vectors = model.get_embeddings(["Python", "Machine Learning", "Docker"])
            >>> len(vectors)
            3
            >>> len(vectors[0])
            384
        """
        if not texts or not isinstance(texts, list):
            logger.warning("[EMBEDDING] Liste de textes vide ou invalide — retourne []")
            return []

        # Filtre les textes non valides avant l'encodage
        valid_texts = [t for t in texts if t and isinstance(t, str)]
        if not valid_texts:
            return []

        logger.debug(f"[EMBEDDING] Vectorisation batch de {len(valid_texts)} textes...")

        # batch_size=32 : optimum CPU/Mémoire pour all-MiniLM-L6-v2
        # show_progress_bar=False : silencieux en mode pipeline
        vectors = self._model.encode(
            valid_texts,
            batch_size=32,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    def get_dimension(self) -> int:
        """
        Retourne la dimension des vecteurs produits par le modèle.

        Returns:
            int: 384 pour all-MiniLM-L6-v2.
        """
        return self._model.get_sentence_embedding_dimension()


# --------------------------------------------------------------------------- #
#  Test standalone                                                             #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    print("=" * 60)
    print("  Test — processing/embeddings.py")
    print("=" * 60)

    # ── Test 1 : Chargement du modèle (Singleton) ────────────────────────────
    print("\n[TEST 1] Chargement du modele (premiere instance)...")
    model_a = EmbeddingModel()
    print(f"  → Dimension du modele : {model_a.get_dimension()}")
    assert model_a.get_dimension() == 384, "ECHEC : dimension attendue = 384"
    print("  → OK — Dimension = 384 confirmee")

    # ── Test 2 : Singleton — même objet retourné ─────────────────────────────
    print("\n[TEST 2] Verification du Singleton (deuxieme instance)...")
    model_b = EmbeddingModel()
    assert model_a is model_b, "ECHEC : le Singleton a cree deux instances differentes"
    print(f"  → model_a is model_b : {model_a is model_b}  (Singleton valide)")

    # ── Test 3 : get_embedding() sur un seul texte ───────────────────────────
    print("\n[TEST 3] Vectorisation d'un seul texte...")
    test_text = "Data Science"
    vector = model_a.get_embedding(test_text)
    print(f"  Texte    : '{test_text}'")
    print(f"  Vecteur  : [{vector[0]:.6f}, {vector[1]:.6f}, ..., {vector[-1]:.6f}]")
    print(f"  Dimension: {len(vector)}")
    assert len(vector) == 384, "ECHEC : dimension attendue = 384"
    print("  → OK — 384 dimensions confirmees")

    # ── Test 4 : get_embeddings() batch ─────────────────────────────────────
    print("\n[TEST 4] Vectorisation en batch (3 textes)...")
    batch_texts = [
        "Machine Learning Engineer with Python and TensorFlow",
        "Experienced Data Analyst proficient in SQL and Power BI",
        "DevOps Engineer skilled in Docker, Kubernetes and CI/CD pipelines",
    ]
    vectors = model_a.get_embeddings(batch_texts)
    print(f"  Nombre de vecteurs : {len(vectors)}")
    print(f"  Dimension de chaque vecteur : {len(vectors[0])}")
    assert len(vectors) == 3
    assert len(vectors[0]) == 384
    print("  → OK — Batch de 3 vecteurs x 384 dimensions")

    # ── Test 5 : Cas limites ─────────────────────────────────────────────────
    print("\n[TEST 5] Cas limites...")
    v_empty  = model_a.get_embedding("")
    v_none   = model_a.get_embedding(None)       # type: ignore
    v_batch0 = model_a.get_embeddings([])
    print(f"  get_embedding('')          → {len(v_empty)} dims (vecteur nul)")
    print(f"  get_embedding(None)        → {len(v_none)} dims (vecteur nul)")
    print(f"  get_embeddings([])         → {v_batch0} (liste vide)")
    print("  → OK — Cas limites geres proprement")

    print("\n[OK] embeddings.py valide. Pipeline Phase 2 pret.")
