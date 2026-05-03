"""
processing/community_summarizer.py
====================================
Synthese des communautes GraphRAG vers ChromaDB — Etape finale Phase 3.

Ce script traduit les communautes mathematiques (ensembles de noeuds NetworkX)
en texte semantique via le LLM, puis indexe ces resumes dans une collection
ChromaDB dediee pour permettre la recherche globale "vue d'ensemble du marche".

Pipeline complet :
    graph_data/smartrecruit_graph.graphml  (sur disque)
        |
        v
    KnowledgeGraphManager.load_graph()
        |
        v
    detect_communities()  ->  [{noeud1, noeud2, ...}, {noeud3, ...}, ...]
        |
        v  [pour chaque communaute]
    GroqClient.generate_text()  ->  Paragraphe de synthese RH (texte libre)
        |
        v
    SentenceTransformer.encode()  ->  vecteur float[384]
        |
        v
    ChromaDB collection "community_insights".upsert()
        |
        v
    Rapport final : N community insights indexes

Deux collections ChromaDB coexistent :
    "cv_embeddings"       : chunks individuels des CVs (Phase 2) — recherche locale
    "community_insights"  : resumes de communautes (Phase 3) — recherche globale

Usage :
    python -m processing.community_summarizer
"""

import sys
import time
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# --------------------------------------------------------------------------- #
#  Resolution du chemin racine                                                 #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    CHROMA_PERSIST_DIR,
    EMBEDDING_MODEL,
)
from generation.llm_client import GroqClient
from graph.networkx_manager import KnowledgeGraphManager


# --------------------------------------------------------------------------- #
#  Constantes                                                                  #
# --------------------------------------------------------------------------- #
COMMUNITY_COLLECTION  = "community_insights"   # Collection ChromaDB dediee
MIN_COMMUNITY_SIZE    = 3                       # Ignorer les micro-communautes isolees
API_DELAY_S           = 2.0                     # Pause entre appels Groq (rate limit)
SEP  = "-" * 65
BOLD = "=" * 65

# Prompt systeme pour la synthese RH
HR_ANALYST_SYSTEM_PROMPT = (
    "Tu es un Analyste RH senior specialise dans la cartographie des viviers de talents. "
    "On te fournit une liste d'entites (candidats, competences, postes, entreprises) "
    "qui forment une communaute semantique dans un graphe de connaissances. "
    "Redige un resume concis en 3 a 4 phrases maximum decrivant l'expertise globale "
    "de ce vivier de talents : quelles competences dominent, quels profils sont representes, "
    "et dans quel secteur ou domaine s'inscrit cette communaute. "
    "Ne fais pas de listes a puces. Redige un paragraphe fluide et professionnel."
)


# --------------------------------------------------------------------------- #
#  Formatage d'une communaute en texte lisible                                #
# --------------------------------------------------------------------------- #
def format_community_as_text(
    community: set,
    graph_manager: KnowledgeGraphManager,
) -> str:
    """
    Convertit un ensemble de noeuds NetworkX en texte structure pour le LLM.

    Organise les noeuds par type (Candidat, Competence, Poste, Entreprise)
    pour faciliter la comprehension contextuelle du modele.

    Args:
        community:     Set d'IDs de noeuds appartenant a la communaute.
        graph_manager: Gestionnaire du graphe global (pour acceder aux attributs).

    Returns:
        str: Texte structure par type de noeud, pret pour le prompt LLM.

    Example:
        "Candidates: Alice Dupont, Hinata Sato
         Skills: Python, Machine Learning, TensorFlow
         Job titles: Data Scientist, ML Engineer
         Companies: DataTech, AI Labs"
    """
    G = graph_manager.global_graph

    groups: dict[str, list[str]] = {
        "Candidat":   [],
        "Competence": [],
        "Poste":      [],
        "Entreprise": [],
        "Unknown":    [],
    }

    for node_id in community:
        attrs = G.nodes.get(node_id, {})
        label = attrs.get("label", node_id)
        ntype = attrs.get("type", "Unknown")
        groups.get(ntype, groups["Unknown"]).append(label)

    # Construction du texte (en anglais pour le LLM multilingue)
    lines = []
    label_map = {
        "Candidat":   "Candidates",
        "Competence": "Skills",
        "Poste":      "Job titles",
        "Entreprise": "Companies",
    }
    for ntype, label in label_map.items():
        members = groups.get(ntype, [])
        if members:
            lines.append(f"{label}: {', '.join(sorted(members))}")

    if groups["Unknown"]:
        lines.append(f"Other entities: {', '.join(sorted(groups['Unknown']))}")

    return "\n".join(lines) if lines else "No entities found in this community."


# --------------------------------------------------------------------------- #
#  Classe principale                                                           #
# --------------------------------------------------------------------------- #
class CommunitySummarizer:
    """
    Orchestrateur de la synthese des communautes GraphRAG.

    Responsabilites :
        1. Charger le graphe global depuis le disque
        2. Detecter les communautes semantiques
        3. Generer un resume textuel par communaute (via Groq)
        4. Vectoriser et indexer dans ChromaDB ("community_insights")

    Attributs publics :
        manager    : KnowledgeGraphManager charge
        llm        : GroqClient initialise
        embedder   : SentenceTransformer charge
        collection : Collection ChromaDB "community_insights"
    """

    def __init__(self) -> None:
        """
        Initialise tous les composants. Echoue rapidement si un composant
        est inaccessible (principe Fail Fast).

        Raises:
            FileNotFoundError: Si le graphe GraphML n'existe pas sur disque.
            EnvironmentError:  Si GROQ_API_KEY est absente.
            RuntimeError:      Si ChromaDB ou le modele d'embedding ne charge pas.
        """
        print(f"\n{BOLD}")
        print("  SmartRecruit AI - Community Summarizer")
        print("  Phase 3 : GraphRAG -> ChromaDB community_insights")
        print(BOLD)

        # ── Graphe global ────────────────────────────────────────────────────
        print("\n[1/4] Chargement du graphe global...")
        self.manager = KnowledgeGraphManager()
        loaded = self.manager.load_graph()

        if not loaded or self.manager.global_graph.number_of_nodes() == 0:
            raise FileNotFoundError(
                "Graphe introuvable ou vide. "
                "Executez d'abord : python scripts/run_graph_batch.py"
            )
        print(
            f"      OK — {self.manager.global_graph.number_of_nodes()} noeuds, "
            f"{self.manager.global_graph.number_of_edges()} aretes."
        )

        # ── Client LLM ──────────────────────────────────────────────────────
        print("\n[2/4] Initialisation du client Groq...")
        self.llm = GroqClient()
        print(f"      Modele : {self.llm.model}")

        # ── Modele d'embedding ───────────────────────────────────────────────
        print(f"\n[3/4] Chargement du modele d'embedding ({EMBEDDING_MODEL})...")
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)
        dim = self.embedder.get_sentence_embedding_dimension()
        print(f"      Modele pret. Dimension : {dim}")

        # ── ChromaDB ─────────────────────────────────────────────────────────
        print(f"\n[4/4] Connexion ChromaDB ({CHROMA_PERSIST_DIR})...")
        persist_path = Path(CHROMA_PERSIST_DIR)
        persist_path.mkdir(parents=True, exist_ok=True)

        client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=Settings(anonymized_telemetry=False),
        )

        # get_or_create_collection : idempotent — relancer ne cree pas de doublons
        self.collection = client.get_or_create_collection(
            name=COMMUNITY_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        print(
            f"      Collection '{COMMUNITY_COLLECTION}' prete. "
            f"Insights existants : {self.collection.count()}"
        )

    # ── Pipeline principal ───────────────────────────────────────────────────

    def run(self) -> int:
        """
        Execute le pipeline complet de synthese des communautes.

        Pour chaque communaute :
            1. Formate les noeuds en texte lisible
            2. Appelle Groq pour generer un resume RH (texte libre)
            3. Vectorise le resume avec SentenceTransformer
            4. Upsert dans ChromaDB avec metadonnees

        Returns:
            int: Nombre de community insights indexes avec succes.
        """
        # Detection des communautes
        print(f"\n{SEP}")
        print("  Detection des communautes...")
        communities = self.manager.detect_communities()

        if not communities:
            print("  Aucune communaute detectee — graphe trop petit ou vide.")
            return 0

        # Filtre des micro-communautes
        filtered = [c for c in communities if len(c) >= MIN_COMMUNITY_SIZE]
        skipped  = len(communities) - len(filtered)

        print(f"  {len(communities)} communaute(s) detectee(s).")
        if skipped:
            print(f"  {skipped} micro-communaute(s) (<{MIN_COMMUNITY_SIZE} noeuds) ignoree(s).")
        print(f"  {len(filtered)} communaute(s) a synthetiser.\n")
        print(SEP)

        success_count = 0

        for idx, community in enumerate(filtered, start=1):
            comm_id = f"comm_{idx}"
            print(f"\n  [{idx}/{len(filtered)}] Communaute #{idx} ({len(community)} noeuds)")

            # ── Formatage ────────────────────────────────────────────────────
            community_text = format_community_as_text(community, self.manager)
            print(f"    Entites : {community_text[:120]}{'...' if len(community_text) > 120 else ''}")

            # ── Generation du resume LLM ─────────────────────────────────────
            prompt = (
                f"Here is a community of talent entities from a knowledge graph:\n\n"
                f"{community_text}\n\n"
                f"Write a concise HR summary (3-4 sentences) describing the expertise "
                f"profile of this talent pool."
            )

            try:
                summary = self.llm.generate_text(
                    prompt=prompt,
                    system_prompt=HR_ANALYST_SYSTEM_PROMPT,
                )
            except RuntimeError as e:
                print(f"    [ERREUR LLM] Communaute #{idx} ignoree : {e}")
                continue
            except Exception as e:
                print(f"    [ERREUR INATTENDUE] Communaute #{idx} : {e}")
                continue

            if not summary or len(summary.strip()) < 10:
                print(f"    [AVERTISSEMENT] Resume vide ou trop court — communaute #{idx} ignoree.")
                continue

            print(f"    Resume ({len(summary)} chars) : {summary[:100]}...")

            # ── Vectorisation ────────────────────────────────────────────────
            try:
                vector = self.embedder.encode(
                    summary,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                ).tolist()
            except Exception as e:
                print(f"    [ERREUR EMBEDDING] Communaute #{idx} : {e}")
                continue

            # ── Metadonnees enrichies ─────────────────────────────────────────
            # Extrait les labels des membres les plus representatifs (max 10)
            top_labels = []
            for node_id in list(community)[:10]:
                attrs = self.manager.global_graph.nodes.get(node_id, {})
                top_labels.append(attrs.get("label", node_id))

            metadata = {
                "community_id":   comm_id,
                "size":           len(community),
                "top_members":    ", ".join(top_labels),
                "summary_length": len(summary),
            }

            # ── Upsert ChromaDB ──────────────────────────────────────────────
            try:
                self.collection.upsert(
                    ids=[comm_id],
                    documents=[summary],
                    embeddings=[vector],
                    metadatas=[metadata],
                )
                print(f"    [OK] Indexe dans ChromaDB — {comm_id} | {len(community)} noeuds")
                success_count += 1
            except Exception as e:
                print(f"    [ERREUR CHROMA] Upsert echoue pour communaute #{idx} : {e}")

            # Pause anti-rate-limit (sauf pour la derniere communaute)
            if idx < len(filtered):
                time.sleep(API_DELAY_S)

        # ── Rapport final ─────────────────────────────────────────────────────
        print(f"\n{SEP}")
        print(f"\n  Synthese terminee.")
        print(f"  Community insights indexes : {success_count}/{len(filtered)}")
        print(f"  Total dans '{COMMUNITY_COLLECTION}' : {self.collection.count()}")

        if success_count > 0:
            print(
                f"\n  La collection '{COMMUNITY_COLLECTION}' est prete pour la"
                f" recherche globale (Phase 4)."
            )

        print(f"\n{BOLD}\n")
        return success_count

    def query_insight(self, query: str, n_results: int = 3) -> list[dict]:
        """
        Recherche semantique dans les community insights.

        Args:
            query:     Requete en langage naturel.
            n_results: Nombre de resultats retournes.

        Returns:
            list[dict]: [{summary, metadata, distance}, ...]
        """
        if self.collection.count() == 0:
            return []

        query_vector = self.embedder.encode(
            query,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).tolist()

        effective_n = min(n_results, self.collection.count())
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=effective_n,
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        for i in range(len(results["ids"][0])):
            hits.append({
                "summary":  results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": round(results["distances"][0][i], 4),
            })
        return hits


# --------------------------------------------------------------------------- #
#  Point d'entree                                                              #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    try:
        summarizer = CommunitySummarizer()
    except FileNotFoundError as e:
        print(f"\n  [ERREUR] {e}")
        sys.exit(1)
    except EnvironmentError as e:
        print(f"\n  [ERREUR] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n  [ERREUR INITIALISATION] {e}")
        sys.exit(1)

    # Execution du pipeline
    n_indexed = summarizer.run()

    # Test de recherche si des insights ont ete indexes
    if n_indexed > 0:
        print("  Test de recherche semantique sur les community insights :")
        print(f"  {'-' * 55}")
        test_queries = [
            "Python developers with machine learning expertise",
            "Healthcare professionals and medical specialists",
        ]
        for query in test_queries:
            print(f"\n  Requete : \"{query}\"")
            hits = summarizer.query_insight(query, n_results=2)
            for i, hit in enumerate(hits, 1):
                sim = round(1 - hit["distance"], 3)
                meta = hit["metadata"]
                print(f"    #{i} Similarite {sim:.1%} | "
                      f"Communaute {meta['community_id']} "
                      f"({meta['size']} membres) : "
                      f"{hit['summary'][:100]}...")
