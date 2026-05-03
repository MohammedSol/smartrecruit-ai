"""
rag/retriever.py
=================
Retriever Hybride LCEL — Coeur du moteur RAG de SmartRecruit AI.

Architecture du retriever :
    Requete utilisateur
        |
        v
    [ChromaDB] base_retriever.as_retriever()
        Recherche semantique dans "community_insights"
        Retourne k=2 Documents (resumes de communautes)
        |
        v  [LCEL pipe |]
    [RunnableLambda] _fetch_mongo_cvs()
        Extrait les noms de candidats des resumes Chroma
        Requete MongoDB : {"name": {"$in": [...]}}
        Convertit en Documents LangChain (3 CVs max)
        Prepend le Community Insight comme contexte global
        |
        v
    Liste finale de Documents
        [Document(community_insight), Document(cv1), Document(cv2), ...]
        |
        v
    [chain.py] PromptTemplate -> Groq LLM -> Reponse finale

Pourquoi ce design ?
    - ChromaDB donne la vue "macro" : quel vivier de talents est pertinent ?
    - MongoDB donne la vue "micro" : quels candidats concrets en font partie ?
    - Le LLM recoit les deux niveaux de contexte pour une reponse riche et sourcee.

Dependances :
    pip install langchain langchain-chroma langchain-huggingface pymongo
"""

import re
import sys
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda
from langchain_huggingface import HuggingFaceEmbeddings
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# --------------------------------------------------------------------------- #
#  Resolution du chemin racine                                                 #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    CHROMA_PERSIST_DIR,
    EMBEDDING_MODEL,
    MONGO_URI,
    MONGO_DB_NAME,
    MONGO_COLLECTION,
)

# --------------------------------------------------------------------------- #
#  Constantes                                                                  #
# --------------------------------------------------------------------------- #
COMMUNITY_COLLECTION = "community_insights"   # Collection ChromaDB Phase 3
MAX_MONGO_CANDIDATES = 3                       # Limite stricte : fenetre contexte LLM
CHROMA_K             = 2                       # Top-k communautes retournees par Chroma


# --------------------------------------------------------------------------- #
#  Initialisation globale des connexions (une seule fois au chargement)       #
# --------------------------------------------------------------------------- #

# Modele d'embedding — meme modele que le pipeline Phase 2 & 3
# HuggingFaceEmbeddings est l'adaptateur LangChain pour sentence-transformers
_embedding_model = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL,
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

# Vectorstore Chroma — connecte a la collection "community_insights"
# Utilise le meme dossier de persistance que le reste du pipeline
_vectorstore = Chroma(
    collection_name=COMMUNITY_COLLECTION,
    embedding_function=_embedding_model,
    persist_directory=str(CHROMA_PERSIST_DIR),
)

# Client MongoDB — connexion partagee au niveau module (pas de reconnexion a chaque appel)
try:
    _mongo_client     = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5_000)
    _mongo_client.admin.command("ping")
    _mongo_collection = _mongo_client[MONGO_DB_NAME][MONGO_COLLECTION]
except ConnectionFailure as e:
    # On ne bloque pas l'import — l'erreur sera levee lors du premier appel retriever
    _mongo_client     = None
    _mongo_collection = None
    print(f"[RETRIEVER] Avertissement : MongoDB inaccessible au demarrage. Detail : {e}")


# --------------------------------------------------------------------------- #
#  Extraction des noms depuis un Community Insight                            #
# --------------------------------------------------------------------------- #
def _extract_candidate_names(page_content: str) -> list[str]:
    """
    Extrait la liste des noms de candidats depuis le contenu d'un Document Chroma.

    Le community insight peut contenir les noms de deux facons :
        1. Injectes dans les metadonnees du document sous la cle "top_members"
        2. Presents dans le texte du resume sous la forme "Candidates: Nom1, Nom2"

    Strategie de parsing (ordre de priorite) :
        1. Regex sur "Candidates:" dans le page_content
        2. Fallback sur le champ metadata["top_members"] si disponible

    Args:
        page_content: Texte du Document LangChain retourne par Chroma.

    Returns:
        list[str]: Liste de noms nettoyes, prets pour la requete MongoDB $in.

    Example:
        >>> _extract_candidate_names("Candidates: Alice Dupont, Hinata Sato\\nSkills: Python")
        ['Alice Dupont', 'Hinata Sato']
    """
    # Regex : capture tout ce qui suit "Candidates:" jusqu'a un saut de ligne ou la fin
    match = re.search(
        r"Candidates\s*:\s*([^\n]+)",
        page_content,
        re.IGNORECASE,
    )

    if match:
        raw_names = match.group(1)
        names = [name.strip() for name in raw_names.split(",") if name.strip()]
        return names

    return []


# --------------------------------------------------------------------------- #
#  Fonction de recuperation MongoDB (coeur du retriever hybride)              #
# --------------------------------------------------------------------------- #
def _fetch_mongo_cvs(chroma_docs: list[Document]) -> list[Document]:
    """
    Enrichit les Community Insights Chroma avec les CVs complets de MongoDB.

    Cette fonction est le maillon central de l'architecture hybride :
        - Entree  : liste de Documents Chroma (resumes de communautes)
        - Sortie  : [Community Insight] + [CV1, CV2, CV3] = contexte complet pour le LLM

    Pipeline interne :
        1. Pour chaque Document Chroma, extrait les noms de candidats
        2. Deduplique la liste de noms (un candidat peut etre dans 2 communautes)
        3. Requete MongoDB avec $in sur le champ "name"
        4. Limite a MAX_MONGO_CANDIDATES pour ne pas saturer le contexte LLM
        5. Convertit chaque doc MongoDB en Document LangChain
        6. Prepend le(s) Community Insight(s) comme premier(s) element(s)

    Gestion des cas limites :
        - MongoDB inaccessible  -> retourne uniquement les docs Chroma
        - Aucun nom extrait     -> retourne uniquement les docs Chroma
        - Aucun CV trouve       -> retourne uniquement les docs Chroma

    Args:
        chroma_docs: Documents LangChain retournes par le base_retriever Chroma.

    Returns:
        list[Document]: Liste combinee [community_insights + cvs_mongodb]
    """
    # Garde-fou : si MongoDB n'est pas disponible, on degrade proprement
    if _mongo_collection is None:
        print("[RETRIEVER] MongoDB non disponible — retour des docs Chroma uniquement.")
        return chroma_docs

    # ── Extraction de tous les noms depuis les documents Chroma ──────────────
    all_names: list[str] = []

    for doc in chroma_docs:
        # Strategie 1 : regex sur le page_content
        names_from_content = _extract_candidate_names(doc.page_content)
        all_names.extend(names_from_content)

        # Strategie 2 : fallback sur les metadonnees ChromaDB
        if not names_from_content and doc.metadata:
            top_members = doc.metadata.get("top_members", "")
            if top_members:
                fallback_names = [n.strip() for n in top_members.split(",") if n.strip()]
                all_names.extend(fallback_names)

    # Deduplification en preservant l'ordre
    seen: set[str] = set()
    unique_names: list[str] = []
    for name in all_names:
        if name not in seen:
            seen.add(name)
            unique_names.append(name)

    # Si aucun nom extrait : on retourne les docs Chroma seuls
    if not unique_names:
        print("[RETRIEVER] Aucun candidat extrait des community insights.")
        return chroma_docs

    # ── Requete MongoDB ──────────────────────────────────────────────────────
    try:
        mongo_docs_raw = list(
            _mongo_collection.find(
                {"name": {"$in": unique_names}},  # Filtre par noms
                {"_id": 0},                        # Exclure l'ObjectId non serialisable
            ).limit(MAX_MONGO_CANDIDATES)
        )
    except Exception as e:
        print(f"[RETRIEVER] Erreur MongoDB lors du fetch : {e}")
        return chroma_docs

    if not mongo_docs_raw:
        print(f"[RETRIEVER] Aucun CV MongoDB trouve pour : {unique_names}")
        return chroma_docs

    # ── Conversion en Documents LangChain ────────────────────────────────────
    mongo_documents: list[Document] = []

    for cv in mongo_docs_raw:
        # Formate le CV en texte lisible pour le LLM
        # On utilise str() plutot que json.dumps() pour la lisibilite humaine
        cv_text = _format_cv_for_llm(cv)

        mongo_documents.append(Document(
            page_content=cv_text,
            metadata={
                "source":   "mongodb",
                "name":     cv.get("name", "Inconnu"),
                "title":    cv.get("title", "N/A"),
                "location": cv.get("location", "N/A"),
                "cv_id":    cv.get("id", "N/A"),
            },
        ))

    print(
        f"[RETRIEVER] {len(mongo_documents)} CV(s) MongoDB recupere(s) "
        f"pour : {[d.metadata['name'] for d in mongo_documents]}"
    )

    # ── Construction de la liste finale ──────────────────────────────────────
    # Ordre : [Community Insights (contexte global)] + [CVs individuels (contexte local)]
    # Le LLM lit les documents dans l'ordre -> le contexte global en premier
    return list(chroma_docs) + mongo_documents


def _format_cv_for_llm(cv: dict) -> str:
    """
    Formate un document CV MongoDB en texte structure pour le LLM.

    Plus lisible que JSON brut. Optimise pour la fenetre de contexte.

    Args:
        cv: Document CV depuis MongoDB (dict Python).

    Returns:
        str: Representation textuelle du CV, ~300-500 tokens.
    """
    lines: list[str] = []

    # En-tete
    lines.append(f"=== CV : {cv.get('name', 'N/A')} ===")
    lines.append(f"Titre      : {cv.get('title', 'N/A')}")
    lines.append(f"Localite   : {cv.get('location', 'N/A')}")

    # Résumé
    if summary := cv.get("summary", ""):
        lines.append(f"Resume     : {summary[:400]}")

    # Competences
    skills = cv.get("skills", [])
    if skills:
        lines.append(f"Competences: {', '.join(str(s) for s in skills[:12])}")

    # Experiences
    for exp in cv.get("experience", [])[:2]:
        if isinstance(exp, dict):
            role    = exp.get("role", exp.get("title", ""))
            company = exp.get("company", "")
            lines.append(f"Experience : {role} chez {company}")

    # Formation
    for edu in cv.get("education", [])[:1]:
        if isinstance(edu, dict):
            degree = edu.get("degree", "")
            school = edu.get("institution", "")
            lines.append(f"Formation  : {degree} — {school}")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  RunnableLambda — adaptateur LCEL                                           #
# --------------------------------------------------------------------------- #
# Encapsule _fetch_mongo_cvs dans un composant LangChain composable
# Permet d'ecrire : base_retriever | fetch_mongo_cvs | prompt | llm
fetch_mongo_cvs = RunnableLambda(_fetch_mongo_cvs)


# --------------------------------------------------------------------------- #
#  Fonction publique : construction du retriever hybride                      #
# --------------------------------------------------------------------------- #
def get_retriever() -> Any:
    """
    Construit et retourne le retriever hybride LCEL.

    Pipeline LCEL :
        base_retriever (Chroma)
            -> recherche dans "community_insights" (k=2)
            -> retourne 2 Documents LangChain

        | RunnableLambda(_fetch_mongo_cvs)
            -> extrait les noms des candidats depuis les resumes
            -> requete MongoDB {"name": {"$in": [...]}}
            -> retourne [community_insights + cvs_complets]

    Usage dans chain.py :
        retriever = get_retriever()
        docs = retriever.invoke("Cherche un data scientist Python")
        # docs = [Document(community_insight), Document(cv_alice), Document(cv_hinata)]

    Returns:
        Runnable LCEL composable avec | prompt | llm dans chain.py.
    """
    # Base retriever : ChromaDB community_insights, top-2 par similarite cosinus
    base_retriever = _vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": CHROMA_K},
    )

    # Retriever hybride : Chroma -> MongoDB enrichment (chaine LCEL)
    hybrid_retriever = base_retriever | fetch_mongo_cvs

    return hybrid_retriever


# --------------------------------------------------------------------------- #
#  Test standalone                                                             #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    print("=" * 65)
    print("  SmartRecruit AI - Test rag/retriever.py")
    print("  Flux : Requete -> ChromaDB -> MongoDB -> Documents")
    print("=" * 65)

    # Verification de la collection ChromaDB
    count = _vectorstore._collection.count()
    print(f"\n  Collection '{COMMUNITY_COLLECTION}' : {count} insight(s)")

    if count == 0:
        print(
            "\n  [!] La collection est vide.\n"
            "  Executez d'abord :\n"
            "    python scripts/run_graph_batch.py\n"
            "    python -m processing.community_summarizer"
        )
        sys.exit(1)

    # Construction du retriever
    print("\n  Construction du retriever hybride...")
    retriever = get_retriever()
    print("  Retriever LCEL pret.")

    # Test de recuperation
    test_query = "Python developer with machine learning experience"
    print(f"\n  Requete test : \"{test_query}\"")
    print("  " + "-" * 55)

    docs = retriever.invoke(test_query)

    print(f"\n  {len(docs)} Document(s) retourne(s) :")
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "chroma")
        name   = doc.metadata.get("name", f"Community #{i}")
        print(f"\n  [{i}] Source : {source.upper()} | {name}")
        print(f"       {doc.page_content[:200]}...")

    print(f"\n  OK - Retriever hybride valide.")
    print("=" * 65)
