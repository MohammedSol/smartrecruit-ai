"""
scripts/run_graph_batch.py
===========================
Job Batch d'extraction du Graphe de Connaissances Global — Etape 3.3 bis.

Ce script orchestre le pipeline complet :
    MongoDB (tous les CVs)
        |
        v  [pour chaque CV]
    format_cv_as_text()          -> texte plat
        |
        v
    GroqClient.extract_json()    -> {"nodes": [...], "edges": [...]}
        |
        v
    build_nx_graph()             -> nx.DiGraph local
        |
        v
    KnowledgeGraphManager.add_subgraph() -> fusion dans le graphe global
        |
        v  [fin de boucle]
    manager.save_graph()         -> graph_data/smartrecruit_graph.graphml

Comportement en cas d'erreur :
    - Si un CV plante (LLM, parsing, MongoDB) : log de l'erreur + passage au suivant.
    - Si MongoDB est inaccessible au démarrage : arrêt immédiat.
    - Si Groq est inaccessible (après 3 retries) : arrêt immédiat + sauvegarde partielle.

Usage :
    python scripts/run_graph_batch.py
    python scripts/run_graph_batch.py --skip-existing   # Charge le graphe existant avant de continuer
    python scripts/run_graph_batch.py --delay 3         # Delai entre appels API (defaut : 2s)
    python scripts/run_graph_batch.py --limit 10        # Traite seulement les N premiers CVs
"""

import argparse
import sys
import time
from pathlib import Path

import networkx as nx
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# --------------------------------------------------------------------------- #
#  Resolution du chemin racine                                                 #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION
from generation.llm_client import GroqClient
from processing.graph_builder import (
    GRAPH_EXTRACTION_PROMPT,
    format_cv_as_text,
    build_nx_graph,
)
from graph.networkx_manager import KnowledgeGraphManager


# --------------------------------------------------------------------------- #
#  Constantes                                                                  #
# --------------------------------------------------------------------------- #
DEFAULT_DELAY_S   = 2.0   # Pause entre chaque appel API (eviter le rate limit Groq)
DEFAULT_LIMIT     = None  # None = tous les CVs
SAVE_CHECKPOINT_N = 10    # Sauvegarde intermediaire tous les N CVs traites


# --------------------------------------------------------------------------- #
#  Helpers d'affichage                                                         #
# --------------------------------------------------------------------------- #
SEP  = "-" * 65
BOLD = "=" * 65


def print_progress(current: int, total: int, cv_name: str, status: str) -> None:
    """Affiche une ligne de progression standardisée."""
    pct = f"{current / total * 100:5.1f}%"
    print(f"  [{pct}] {current:>3}/{total}  {status}  {cv_name}")


def print_final_stats(manager: KnowledgeGraphManager, stats_run: dict) -> None:
    """Affiche le rapport final du batch."""
    graph_stats = manager.get_stats()

    print(f"\n{BOLD}")
    print("  RAPPORT FINAL — Batch GraphRAG")
    print(BOLD)
    print(f"\n  CVs traites      : {stats_run['processed']}/{stats_run['total']}")
    print(f"  CVs en erreur    : {stats_run['errors']}")
    print(f"  CVs sans graphe  : {stats_run['empty']}")
    print(f"  Temps total      : {stats_run['elapsed']:.1f}s")
    print(f"  Temps moyen/CV   : {stats_run['elapsed'] / max(stats_run['processed'], 1):.1f}s")
    print(f"\n  -- Graphe Global --")
    print(f"  Noeuds totaux    : {graph_stats['nodes']}")
    print(f"  Aretes totales   : {graph_stats['edges']}")
    print(f"  Densite          : {graph_stats['density']}")
    print(f"\n  Distribution noeuds :")
    for ntype, count in sorted(graph_stats['node_types'].items()):
        print(f"    {ntype:<15} : {count}")
    print(f"\n  Distribution aretes :")
    for rel, count in sorted(graph_stats['edge_relations'].items()):
        print(f"    {rel:<25} : {count}")
    print()


# --------------------------------------------------------------------------- #
#  Traitement d'un CV                                                          #
# --------------------------------------------------------------------------- #
def process_cv(cv: dict, llm: GroqClient) -> nx.DiGraph:
    """
    Extrait le sous-graphe d'un CV via le LLM.

    Pipeline :
        1. format_cv_as_text()    -> texte plat
        2. llm.extract_json()     -> {"nodes": [...], "edges": [...]}
        3. build_nx_graph()       -> nx.DiGraph

    Args:
        cv:  Dictionnaire CV depuis MongoDB.
        llm: Client Groq initialise.

    Returns:
        nx.DiGraph: Sous-graphe extrait. Peut etre vide si l'extraction echoue.

    Raises:
        RuntimeError: Propagee si le LLM est inaccessible (erreur critique).
    """
    # Formatage du CV
    cv_text = format_cv_as_text(cv)
    if not cv_text.strip():
        return nx.DiGraph()

    # Appel LLM
    prompt = (
        f"Extract entities and relations from the following CV:\n\n"
        f"{cv_text}\n\n"
        f"Return ONLY the JSON object. No explanation."
    )
    extracted = llm.extract_json(
        prompt=prompt,
        system_prompt=GRAPH_EXTRACTION_PROMPT,
    )

    # Validation minimale
    if not isinstance(extracted, dict) or \
       ("nodes" not in extracted and "edges" not in extracted):
        return nx.DiGraph()

    return build_nx_graph(extracted, cv_name=cv.get("name", "?"))


# --------------------------------------------------------------------------- #
#  Boucle principale                                                           #
# --------------------------------------------------------------------------- #
def run_batch(
    delay_s: float = DEFAULT_DELAY_S,
    limit: int = None,
    skip_existing: bool = False,
) -> None:
    """
    Orchestre l'extraction du graphe sur tous les CVs MongoDB.

    Args:
        delay_s:       Pause en secondes entre chaque appel LLM.
        limit:         Nombre max de CVs a traiter (None = tous).
        skip_existing: Si True, charge le graphe existant avant de commencer.
    """
    start_time = time.time()

    print(f"\n{BOLD}")
    print("  SmartRecruit AI - Batch GraphRAG")
    print("  Etape 3.3 bis : MongoDB -> Groq NER -> NetworkX Global")
    print(BOLD)

    # ── 1. Connexion MongoDB ─────────────────────────────────────────────────
    print(f"\n[1/4] Connexion MongoDB : {MONGO_URI}")
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5_000)
        mongo_client.admin.command("ping")
        collection = mongo_client[MONGO_DB_NAME][MONGO_COLLECTION]
        total_cvs  = collection.count_documents({})
        print(f"      OK — {total_cvs} CVs dans '{MONGO_DB_NAME}.{MONGO_COLLECTION}'")
    except ConnectionFailure as e:
        print(f"\n      ECHEC — MongoDB inaccessible : {e}")
        print("      Verifiez : docker compose ps")
        sys.exit(1)

    if total_cvs == 0:
        print("\n      La collection est vide. Lancez le pipeline Producer + Consumer d'abord.")
        sys.exit(1)

    # Limit effective
    effective_total = min(total_cvs, limit) if limit else total_cvs
    if limit:
        print(f"      Mode limite actif : traitement des {effective_total} premiers CVs.")

    # ── 2. Initialisation LLM ───────────────────────────────────────────────
    print(f"\n[2/4] Initialisation du client Groq...")
    try:
        llm = GroqClient()
        print(f"      Modele : {llm.model}")
    except EnvironmentError as e:
        print(f"\n      ECHEC — {e}")
        sys.exit(1)

    # ── 3. Initialisation du gestionnaire de graphe ──────────────────────────
    print(f"\n[3/4] Initialisation de KnowledgeGraphManager...")
    manager = KnowledgeGraphManager()

    if skip_existing:
        loaded = manager.load_graph()
        if loaded:
            print(
                f"      Graphe existant charge : "
                f"{manager.global_graph.number_of_nodes()} noeuds, "
                f"{manager.global_graph.number_of_edges()} aretes."
            )
        else:
            print("      Aucun graphe existant — extraction complete.")
    else:
        print("      Nouveau graphe (mode par defaut — extraction complete).")

    # ── 4. Boucle principale ─────────────────────────────────────────────────
    print(f"\n[4/4] Extraction en cours ({effective_total} CVs)...\n")
    print(f"  {SEP}")

    stats = {
        "total":     effective_total,
        "processed": 0,
        "errors":    0,
        "empty":     0,
        "elapsed":   0.0,
    }

    cursor = collection.find({}, {"_id": 0}).limit(effective_total)

    for idx, cv in enumerate(cursor, start=1):
        cv_name = cv.get("name", "Inconnu")
        cv_id   = cv.get("id", "?")[:8]

        try:
            subgraph = process_cv(cv, llm)

            if subgraph.number_of_nodes() == 0:
                print_progress(idx, effective_total, cv_name, "[VIDE ]")
                stats["empty"] += 1
            else:
                manager.add_subgraph(subgraph)
                n_nodes = subgraph.number_of_nodes()
                n_edges = subgraph.number_of_edges()
                print_progress(
                    idx, effective_total, cv_name,
                    f"[OK   ]  +{n_nodes} noeuds  +{n_edges} aretes"
                )
            stats["processed"] += 1

        except RuntimeError as e:
            # Erreur LLM critique (API down, cle invalide) — arrêt propre
            print(f"\n  [CRITIQUE] Erreur LLM irrécuperable : {e}")
            print(f"  Sauvegarde du graphe partiel ({stats['processed']} CVs)...")
            manager.save_graph()
            mongo_client.close()
            sys.exit(1)

        except Exception as e:
            # Erreur isolée (parsing JSON, CV mal formé) — on continue
            print_progress(idx, effective_total, cv_name, f"[ERREUR] {str(e)[:60]}")
            stats["errors"] += 1

        # Sauvegarde intermediaire tous les N CVs
        if stats["processed"] > 0 and stats["processed"] % SAVE_CHECKPOINT_N == 0:
            manager.save_graph()
            print(f"\n  [CHECKPOINT] Graphe intermediaire sauvegarde ({stats['processed']} CVs).\n")

        # Pause anti-rate-limit (sauf pour le dernier CV)
        if idx < effective_total:
            time.sleep(delay_s)

    print(f"  {SEP}")

    # ── 5. Sauvegarde finale ─────────────────────────────────────────────────
    print(f"\n[5/5] Sauvegarde du graphe global...")
    if manager.global_graph.number_of_nodes() > 0:
        saved_path = manager.save_graph()
        print(f"      Fichier : {saved_path}")
    else:
        print("      Graphe vide — aucune sauvegarde.")

    # ── 6. Detection de communautes ──────────────────────────────────────────
    if manager.global_graph.number_of_nodes() >= 2:
        print(f"\n[6/6] Detection de communautes...")
        try:
            communities = manager.detect_communities()
            print(f"      {len(communities)} communaute(s) detectee(s) :")
            for i, community in enumerate(communities[:5], 1):  # Affiche les 5 plus grandes
                labels = [
                    manager.global_graph.nodes[n].get("label", n)
                    for n in list(community)[:6]  # Max 6 membres affiches
                ]
                suffix = f"... (+{len(community) - 6})" if len(community) > 6 else ""
                print(f"      #{i} ({len(community)} noeuds) : {', '.join(labels)}{suffix}")
        except RuntimeError as e:
            print(f"      Detection de communautes echouee : {e}")

    # ── Rapport final ────────────────────────────────────────────────────────
    stats["elapsed"] = time.time() - start_time
    print_final_stats(manager, stats)

    mongo_client.close()


# --------------------------------------------------------------------------- #
#  Point d'entree CLI                                                          #
# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SmartRecruit AI — Batch GraphRAG : MongoDB -> NetworkX global graph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_S,
        metavar="SECONDES",
        help=f"Pause entre chaque appel API Groq (defaut : {DEFAULT_DELAY_S}s)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Traiter seulement les N premiers CVs (utile pour les tests)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Charger le graphe existant depuis le disque avant de continuer",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_batch(
        delay_s=args.delay,
        limit=args.limit,
        skip_existing=args.skip_existing,
    )
