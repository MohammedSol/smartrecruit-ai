"""
processing/graph_builder.py
============================
Extracteur de graphe de connaissances RH via LLM (Etape 3.2 — Hybrid GraphRAG).

Flux :
    MongoDB (CV brut JSON)
        |
        v
    format_cv_as_text()       -> Texte plat lisible par le LLM
        |
        v
    GroqClient.extract_json() -> {"nodes": [...], "edges": [...]}
        |
        v
    build_nx_graph()          -> nx.DiGraph() peuple
        |
        v
    extract_graph_for_cv()    -> nx.DiGraph() retourne (orchestre les 3 etapes)

Architecture :
    Ce module est le "cerveau d'extraction" du pipeline GraphRAG.
    Il transforme des CVs non structures en un graphe de connaissances
    exploitable par les algorithmes de detection de communautes (Phase 3.3).

    Le graphe NetworkX est construit en memoire (in-process) — pas de base
    de graphe externe (pas de Neo4j). Il sera serialise plus tard si besoin.

Ontologie du graphe :
    Noeuds : Candidat | Competence | Poste | Entreprise
    Aretes : MAITRISE | A_TRAVAILLE_COMME | A_TRAVAILLE_CHEZ

Dependances :
    pip install networkx pymongo python-dotenv groq

Usage :
    python -m processing.graph_builder
"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import networkx as nx
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# --------------------------------------------------------------------------- #
#  Resolution chemin racine                                                    #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION
from generation.llm_client import GroqClient

# --------------------------------------------------------------------------- #
#  Logger                                                                      #
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Ontologie du graphe (valeurs autorisees)                                   #
# --------------------------------------------------------------------------- #
ALLOWED_NODE_TYPES = {"Candidat", "Competence", "Poste", "Entreprise"}
ALLOWED_RELATIONS  = {"MAITRISE", "A_TRAVAILLE_COMME", "A_TRAVAILLE_CHEZ"}

# --------------------------------------------------------------------------- #
#  Prompt System — NER specialise RH                                           #
# --------------------------------------------------------------------------- #
GRAPH_EXTRACTION_PROMPT = """[ignoring loop detection]
You are an NER system specialized in HR data extraction.

Given a CV text, return a single JSON object with two keys: "nodes" and "edges".

Each node has: "id" (lowercase snake_case string), "type" (one of: Candidat, Competence, Poste, Entreprise), "label" (display name).
Each edge has: "source" (node id), "relation" (one of: MAITRISE, A_TRAVAILLE_COMME, A_TRAVAILLE_CHEZ), "target" (node id).

The relation MAITRISE links a Candidat to a Competence they master.
The relation A_TRAVAILLE_COMME links a Candidat to a Poste (job title) they held.
The relation A_TRAVAILLE_CHEZ links a Candidat to an Entreprise where they worked.

Rules:
- Output raw JSON only. No markdown, no code fences, no explanation.
- Node IDs must be unique snake_case strings derived from the label.
- Limit output to at most 8 skills, 3 job titles, and 3 companies.
- If no data can be extracted, return: {"nodes": [], "edges": []}
"""


# --------------------------------------------------------------------------- #
#  Utilitaire : Formatage du CV en texte plat                                 #
# --------------------------------------------------------------------------- #
def format_cv_as_text(cv: dict) -> str:
    """
    Convertit un document CV (dict MongoDB) en texte plat lisible par le LLM.

    Privilege la densite d'information sur la mise en forme. Le LLM n'a pas
    besoin de HTML ou de Markdown — un texte structure en sections suffit.

    Args:
        cv: Dictionnaire CV au format canonique SmartRecruit.

    Returns:
        str: Representation textuelle du CV, optimisee pour l'extraction NER.

    Example:
        >>> text = format_cv_as_text({"name": "Alice", "title": "ML Engineer", ...})
        >>> print(text[:100])
        "CANDIDATE: Alice | TITLE: ML Engineer | LOCATION: Paris..."
    """
    lines = []

    # En-tete candidat
    name     = cv.get("name", "Unknown")
    title    = cv.get("title", "")
    location = cv.get("location", "")
    lines.append(f"CANDIDATE: {name} | TITLE: {title} | LOCATION: {location}")

    # Résumé
    if summary := cv.get("summary", ""):
        lines.append(f"SUMMARY: {summary[:500]}")  # Troncature a 500 chars

    # Competences
    skills = cv.get("skills", [])
    if skills:
        skills_str = ", ".join(str(s) for s in skills[:15])  # Max 15 skills
        lines.append(f"SKILLS: {skills_str}")

    # Experiences professionnelles
    experiences = cv.get("experience", [])
    if experiences:
        lines.append("EXPERIENCE:")
        for exp in experiences[:3]:  # Max 3 experiences
            if isinstance(exp, dict):
                company  = exp.get("company", "")
                role     = exp.get("role", exp.get("title", ""))
                duration = exp.get("duration", exp.get("years", ""))
                lines.append(f"  - Role: {role} | Company: {company} | Duration: {duration}")

    # Formation
    education = cv.get("education", [])
    if education:
        lines.append("EDUCATION:")
        for edu in education[:2]:  # Max 2 formations
            if isinstance(edu, dict):
                degree      = edu.get("degree", "")
                institution = edu.get("institution", "")
                lines.append(f"  - {degree} at {institution}")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  Construction du graphe NetworkX depuis le JSON extrait                     #
# --------------------------------------------------------------------------- #
def build_nx_graph(extracted: dict, cv_name: str = "unknown") -> nx.DiGraph:
    """
    Construit un graphe NetworkX oriente depuis les donnees extraites par le LLM.

    Validation :
        - Filtre les types de noeuds non autorises (defense en profondeur)
        - Filtre les types de relations non autorises
        - Ignore les aretes dont source ou cible est absente dans les noeuds
        - Ajoute les attributs de type et label sur chaque noeud

    Args:
        extracted: Dict {"nodes": [...], "edges": [...]} retourne par extract_json().
        cv_name:   Nom du CV (pour les logs de debug).

    Returns:
        nx.DiGraph: Graphe oriente. Peut etre vide si l'extraction a echoue.
    """
    G = nx.DiGraph()

    nodes = extracted.get("nodes", [])
    edges = extracted.get("edges", [])

    if not isinstance(nodes, list) or not isinstance(edges, list):
        logger.warning(f"[GRAPH] Format inattendu pour '{cv_name}' — noeuds ou aretes non-liste.")
        return G

    # ── Injection des noeuds ─────────────────────────────────────────────────
    valid_node_ids = set()
    skipped_nodes  = 0

    for node in nodes:
        if not isinstance(node, dict):
            skipped_nodes += 1
            continue

        node_id   = str(node.get("id", "")).strip().lower()
        node_type = str(node.get("type", "")).strip()
        label     = str(node.get("label", node_id)).strip()

        if not node_id:
            skipped_nodes += 1
            continue

        if node_type not in ALLOWED_NODE_TYPES:
            logger.debug(
                f"[GRAPH] Noeud ignore (type '{node_type}' non autorise) : '{node_id}'"
            )
            skipped_nodes += 1
            continue

        G.add_node(node_id, type=node_type, label=label)
        valid_node_ids.add(node_id)

    # ── Injection des aretes ─────────────────────────────────────────────────
    valid_edges   = 0
    skipped_edges = 0

    for edge in edges:
        if not isinstance(edge, dict):
            skipped_edges += 1
            continue

        source   = str(edge.get("source", "")).strip().lower()
        relation = str(edge.get("relation", "")).strip().upper()
        target   = str(edge.get("target", "")).strip().lower()

        # Validation des champs obligatoires
        if not source or not relation or not target:
            skipped_edges += 1
            continue

        # Filtre : relation non autorisee
        if relation not in ALLOWED_RELATIONS:
            logger.debug(
                f"[GRAPH] Arete ignoree (relation '{relation}' non autorisee) : "
                f"'{source}' -> '{target}'"
            )
            skipped_edges += 1
            continue

        # Filtre : noeuds source ou cible absent du graphe
        if source not in valid_node_ids or target not in valid_node_ids:
            # Auto-ajout si le noeud manquant peut etre infere
            for missing_id in [source, target]:
                if missing_id not in valid_node_ids:
                    G.add_node(missing_id, type="Unknown", label=missing_id)
                    valid_node_ids.add(missing_id)
                    logger.debug(f"[GRAPH] Noeud auto-ajoute (reference dans une arete) : '{missing_id}'")

        G.add_edge(source, target, relation=relation)
        valid_edges += 1

    logger.debug(
        f"[GRAPH] '{cv_name}' -> {G.number_of_nodes()} noeuds "
        f"({skipped_nodes} ignores), {G.number_of_edges()} aretes "
        f"({skipped_edges} ignorees)"
    )
    return G


# --------------------------------------------------------------------------- #
#  Fonction principale d'extraction                                            #
# --------------------------------------------------------------------------- #
def extract_graph_for_cv(cv: dict, llm_client: GroqClient) -> nx.DiGraph:
    """
    Orchestre l'extraction complete : CV dict -> Graphe NetworkX.

    Pipeline interne :
        1. format_cv_as_text()   : CV dict -> texte plat
        2. llm_client.extract_json() : texte -> {"nodes": ..., "edges": ...}
        3. build_nx_graph()      : JSON -> nx.DiGraph

    Gestion d'erreurs :
        - Si le LLM retourne un JSON invalide   -> graphe vide
        - Si le LLM est inaccessible            -> RuntimeError propagee
        - Si le CV est mal forme                -> graphe vide avec log warning

    Args:
        cv:         Dictionnaire CV au format canonique SmartRecruit.
        llm_client: Instance GroqClient initialisee.

    Returns:
        nx.DiGraph: Graphe de connaissances extrait. Peut etre vide.
    """
    cv_name = cv.get("name", "Inconnu")
    cv_id   = cv.get("id",   str(cv.get("_id", "unknown")))

    logger.info(f"[GRAPH] Extraction pour : {cv_name} ({cv_id[:8]}...)")

    # ── Etape 1 : Formatage du CV ────────────────────────────────────────────
    cv_text = format_cv_as_text(cv)
    if not cv_text.strip():
        logger.warning(f"[GRAPH] CV '{cv_name}' vide apres formatage — graphe vide retourne.")
        return nx.DiGraph()

    # ── Etape 2 : Appel LLM ─────────────────────────────────────────────────
    prompt = (
        f"Extract entities and relations from the following CV:\n\n"
        f"{cv_text}\n\n"
        f"Return ONLY the JSON object as specified. No explanation."
    )

    try:
        extracted = llm_client.extract_json(
            prompt=prompt,
            system_prompt=GRAPH_EXTRACTION_PROMPT,
        )
    except RuntimeError as e:
        logger.error(f"[GRAPH] Echec appel LLM pour '{cv_name}' : {e}")
        raise  # Propagee — erreur critique (API down, cle invalide)
    except Exception as e:
        logger.error(f"[GRAPH] Erreur inattendue lors de l'appel LLM pour '{cv_name}' : {e}")
        return nx.DiGraph()

    # Validation minimale de la structure retournee
    if not isinstance(extracted, dict) or ("nodes" not in extracted and "edges" not in extracted):
        logger.warning(
            f"[GRAPH] JSON extrait invalide pour '{cv_name}'. "
            f"Contenu : {str(extracted)[:200]}"
        )
        return nx.DiGraph()

    # ── Etape 3 : Construction du graphe ─────────────────────────────────────
    G = build_nx_graph(extracted, cv_name=cv_name)

    logger.info(
        f"[GRAPH] '{cv_name}' -> {G.number_of_nodes()} noeuds, "
        f"{G.number_of_edges()} aretes extraites."
    )
    return G


# --------------------------------------------------------------------------- #
#  Utilitaire : Affichage du graphe dans le terminal                          #
# --------------------------------------------------------------------------- #
def print_graph_summary(G: nx.DiGraph, cv_name: str = "") -> None:
    """
    Affiche un resume lisible du graphe dans le terminal.

    Args:
        G:       Graphe NetworkX a afficher.
        cv_name: Nom du CV pour l'en-tete.
    """
    sep = "-" * 65
    print(f"\n{sep}")
    if cv_name:
        print(f"  Graphe pour : {cv_name}")
    print(f"  Noeuds  : {G.number_of_nodes()}")
    print(f"  Aretes  : {G.number_of_edges()}")
    print(sep)

    # Noeuds par type
    nodes_by_type: dict[str, list] = {}
    for node_id, attrs in G.nodes(data=True):
        ntype = attrs.get("type", "Unknown")
        nodes_by_type.setdefault(ntype, []).append(
            attrs.get("label", node_id)
        )

    print("\n  Noeuds par type :")
    for ntype in sorted(nodes_by_type):
        items = ", ".join(nodes_by_type[ntype])
        print(f"    [{ntype}] : {items}")

    # Relations
    print("\n  Relations :")
    if G.number_of_edges() == 0:
        print("    (aucune)")
    else:
        for source, target, attrs in G.edges(data=True):
            src_label = G.nodes[source].get("label", source)
            tgt_label = G.nodes[target].get("label", target)
            relation  = attrs.get("relation", "?")
            print(f"    {src_label:25} --[{relation}]--> {tgt_label}")

    print(f"{sep}\n")


# --------------------------------------------------------------------------- #
#  Point d'entree : Test end-to-end MongoDB -> Groq -> NetworkX               #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    print("=" * 65)
    print("  SmartRecruit AI - Test processing/graph_builder.py")
    print("  Flux : MongoDB -> Groq (NER) -> NetworkX DiGraph")
    print("=" * 65)

    # ── 1. Connexion MongoDB ─────────────────────────────────────────────────
    print(f"\n[1/4] Connexion MongoDB : {MONGO_URI}")
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5_000)
        mongo_client.admin.command("ping")
        collection = mongo_client[MONGO_DB_NAME][MONGO_COLLECTION]
        total_cvs  = collection.count_documents({})
        print(f"  OK - {total_cvs} CVs disponibles dans '{MONGO_DB_NAME}.{MONGO_COLLECTION}'")
    except ConnectionFailure as e:
        print(f"\n  ECHEC - Connexion MongoDB impossible : {e}")
        print("  Verifiez que Docker est en cours : docker compose ps")
        sys.exit(1)

    if total_cvs == 0:
        print("\n  La collection est vide. Lancez d'abord le pipeline Producer + Consumer.")
        sys.exit(1)

    # ── 2. Recuperation d'UN CV ─────────────────────────────────────────────
    print("\n[2/4] Recuperation d'un CV depuis MongoDB...")
    cv = collection.find_one(
        {},
        {"_id": 0}  # Exclure l'ObjectId (non serialisable par defaut)
    )
    if not cv:
        print("  Aucun CV trouve.")
        sys.exit(1)

    cv_name = cv.get("name", "Inconnu")
    cv_id   = cv.get("id", "?")
    print(f"  CV selectionne : {cv_name} ({cv.get('title', 'N/A')})")
    print(f"  ID             : {cv_id}")

    # ── 3. Formatage du CV ──────────────────────────────────────────────────
    print("\n[3/4] Formatage du CV en texte plat...")
    cv_text = format_cv_as_text(cv)
    print(f"  Texte genere ({len(cv_text)} caracteres) :")
    print("  " + cv_text[:300].replace("\n", "\n  "))

    # ── 4. Initialisation LLM + Extraction du graphe ────────────────────────
    print("\n[4/4] Appel Groq (llama3-70b) pour extraction NER...")
    try:
        llm = GroqClient()
        print(f"  Modele Groq : {llm.model}")
    except EnvironmentError as e:
        print(f"\n  ECHEC - {e}")
        sys.exit(1)

    try:
        G = extract_graph_for_cv(cv, llm)
    except RuntimeError as e:
        print(f"\n  ECHEC extraction LLM : {e}")
        sys.exit(1)

    # ── Affichage du resume ──────────────────────────────────────────────────
    if G.number_of_nodes() == 0:
        print("\n  AVERTISSEMENT : Graphe vide — le LLM n'a extrait aucune entite.")
        print("  Verifiez votre GROQ_API_KEY et les logs ci-dessus.")
    else:
        print_graph_summary(G, cv_name=cv_name)
        print(f"  Validation : Flux MongoDB -> Groq -> NetworkX FONCTIONNE.")

    mongo_client.close()
