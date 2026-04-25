"""
processing/chunking.py
======================
Module de découpage de texte (Chunking) pour les CVs.

Rôle dans le pipeline :
    CV JSON (summary + expériences) ──► chunk_text() ──► liste de chunks
    Les chunks sont ensuite vectorisés par embeddings.py, puis indexés dans ChromaDB.

Pourquoi le chunking ?
    Les modèles d'embedding ont une limite de tokens (~256 pour all-MiniLM-L6-v2).
    Un CV complet dépasse souvent cette limite. On le découpe en morceaux cohérents
    ("chunks") qui respectent la fenêtre contextuelle du modèle.

Paramètres choisis :
    chunk_size=500   : ~100 mots par chunk — bon équilibre contexte/précision pour des CVs.
    chunk_overlap=50 : chevauchement de 50 caractères entre chunks consécutifs.
                       Évite de couper une phrase en plein milieu et garantit
                       la continuité sémantique entre deux chunks adjacents.

Dépendance :
    pip install langchain-text-splitters
    (inclus dans langchain — déjà dans requirements.txt)
"""

import logging
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

# --------------------------------------------------------------------------- #
#  Logger du module                                                            #
# --------------------------------------------------------------------------- #
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Configuration du splitter (instancié une seule fois au niveau module)      #
# --------------------------------------------------------------------------- #
_CHUNK_SIZE    = 500   # Taille maximale d'un chunk en caractères
_CHUNK_OVERLAP = 50    # Chevauchement en caractères entre deux chunks consécutifs

# RecursiveCharacterTextSplitter tente d'abord de couper sur "\n\n" (paragraphe),
# puis "\n" (ligne), puis " " (espace), et enfin "" (caractère) — par ordre de
# priorité décroissante — pour maximiser la cohérence sémantique de chaque chunk.
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=_CHUNK_SIZE,
    chunk_overlap=_CHUNK_OVERLAP,
    length_function=len,
    separators=["\n\n", "\n", ".", " ", ""],  # Ordre de découpe pour les CVs
)


def chunk_text(text: Optional[str]) -> list[str]:
    """
    Découpe un texte long en une liste de chunks sémantiquement cohérents.

    Cas gérés proprement :
        - text est None                 → retourne []
        - text n'est pas une str        → retourne [] + warning dans les logs
        - text est vide après .strip()  → retourne []
        - text est court (< chunk_size) → retourne [text] (1 seul chunk intact)

    Args:
        text: Le texte brut à découper (summary d'un CV, section expérience, etc.)

    Returns:
        list[str]: Liste de chunks non vides, prêts pour la vectorisation.

    Example:
        >>> chunks = chunk_text("Long CV summary with many experiences...")
        >>> len(chunks)  # Dépend de la longueur du texte
        3
    """
    # ── Validation de l'entrée ──────────────────────────────────────────────
    if text is None:
        logger.debug("[CHUNKING] Texte None reçu → retourne []")
        return []

    if not isinstance(text, str):
        logger.warning(
            f"[CHUNKING] Type inattendu : {type(text).__name__} (attendu : str) → retourne []"
        )
        return []

    text_stripped = text.strip()
    if not text_stripped:
        logger.debug("[CHUNKING] Texte vide après strip() → retourne []")
        return []

    # ── Découpage ──────────────────────────────────────────────────────────
    chunks = _splitter.split_text(text_stripped)

    # Filtrer les éventuels chunks vides générés par le splitter
    chunks = [c.strip() for c in chunks if c.strip()]

    logger.debug(f"[CHUNKING] {len(chunks)} chunk(s) générés depuis {len(text_stripped)} caractères")
    return chunks


def chunk_cv(cv: dict) -> list[str]:
    """
    Utilitaire de haut niveau : extrait et découpe les sections textuelles d'un CV JSON.

    Sections extraites (dans l'ordre) :
        - summary        : résumé du profil
        - title          : intitulé du poste
        - experiences    : descriptions de postes (champ "description" de chaque dict)
        - skills         : liste de compétences (jointe en une chaîne)

    Args:
        cv: Dictionnaire CV au format canonique SmartRecruit.

    Returns:
        list[str]: Tous les chunks issus des sections textuelles du CV.
    """
    if not isinstance(cv, dict):
        logger.warning(f"[CHUNKING] chunk_cv() attend un dict, reçu {type(cv).__name__}")
        return []

    raw_parts: list[str] = []

    # Titre du poste
    if title := cv.get("title", ""):
        raw_parts.append(str(title))

    # Résumé du profil (section la plus riche sémantiquement)
    if summary := cv.get("summary", ""):
        raw_parts.append(str(summary))

    # Expériences professionnelles
    for exp in cv.get("experience", []):
        if isinstance(exp, dict):
            desc = exp.get("description", "")
            if desc:
                raw_parts.append(str(desc))

    # Compétences (jointes en une phrase pour la vectorisation)
    skills = cv.get("skills", [])
    if skills and isinstance(skills, list):
        raw_parts.append("Skills: " + ", ".join(str(s) for s in skills))

    # Découpage de chaque partie collectée
    all_chunks: list[str] = []
    for part in raw_parts:
        all_chunks.extend(chunk_text(part))

    logger.debug(
        f"[CHUNKING] CV '{cv.get('name', '?')}' → {len(all_chunks)} chunk(s) total"
    )
    return all_chunks


# --------------------------------------------------------------------------- #
#  Test standalone                                                             #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    print("=" * 60)
    print("  Test — processing/chunking.py")
    print("=" * 60)

    # ── Test 1 : texte normal ───────────────────────────────────────────────
    sample_text = (
        "Experienced Data Scientist with over 8 years in the industry. "
        "Specializing in machine learning, natural language processing, and big data pipelines. "
        "Proven track record of delivering end-to-end ML solutions at scale. "
        "Led a team of 5 engineers to build a real-time recommendation engine serving 2M users. "
        "Proficient in Python, Spark, TensorFlow, and cloud platforms (AWS, GCP). "
        "Strong communicator with experience presenting results to C-level stakeholders. "
        "Holds an MSc in Computer Science from Université Paris-Saclay."
    )

    print(f"\n[TEST 1] Texte source ({len(sample_text)} caractères) :")
    print(f"  '{sample_text[:80]}...'")
    print()

    chunks = chunk_text(sample_text)
    print(f"  → {len(chunks)} chunk(s) générés :\n")
    for i, chunk in enumerate(chunks, 1):
        print(f"  Chunk {i} ({len(chunk)} chars) : '{chunk[:70]}...'")

    # ── Test 2 : cas limites ────────────────────────────────────────────────
    print("\n[TEST 2] Cas limites :")
    print(f"  None        → {chunk_text(None)}")
    print(f"  ''          → {chunk_text('')}")
    print(f"  123 (int)   → {chunk_text(123)}")          # type: ignore
    print(f"  'court'     → {chunk_text('court texte')}") # texte court < chunk_size

    # ── Test 3 : chunk_cv() ─────────────────────────────────────────────────
    print("\n[TEST 3] chunk_cv() sur un CV JSON factice :")
    fake_cv = {
        "name": "Alice Dupont",
        "title": "Machine Learning Engineer",
        "summary": "Passionate ML engineer with 5 years of experience building NLP systems.",
        "experience": [
            {"company": "TechCorp", "description": "Developed a document classification pipeline using BERT."},
            {"company": "DataLab", "description": "Built and deployed a RAG chatbot with LangChain and OpenAI."},
        ],
        "skills": ["Python", "PyTorch", "LangChain", "Docker", "Kafka", "MongoDB"],
    }
    cv_chunks = chunk_cv(fake_cv)
    print(f"  → {len(cv_chunks)} chunk(s) total pour '{fake_cv['name']}'")
    for i, c in enumerate(cv_chunks, 1):
        print(f"    [{i}] ({len(c)} chars) {c[:70]}")

    print("\n[OK] chunking.py validé.")
