"""
graph/networkx_manager.py
=========================
Gestionnaire centralisé du Graphe de Connaissances Global — Etape 3.3.

Rôle dans le pipeline GraphRAG :
    Chaque appel à graph_builder.extract_graph_for_cv() produit un
    nx.DiGraph local (sous-graphe d'un seul CV). Ce module fusionne
    tous ces sous-graphes en un graphe global, le persiste sur disque
    et y applique des algorithmes de détection de communautés.

Architecture :
    ┌─────────────────────────────────────────────────────────────────┐
    │  extract_graph_for_cv(cv1) -> G1 (DiGraph)                      │
    │  extract_graph_for_cv(cv2) -> G2 (DiGraph)                      │
    │                 |                                               │
    │                 v                                               │
    │  KnowledgeGraphManager.add_subgraph(G1)                         │
    │  KnowledgeGraphManager.add_subgraph(G2)                         │
    │                 |                                               │
    │                 v                                               │
    │  global_graph : noeuds fusionnés, arêtes dédupliquées           │
    │                 |                                               │
    │                 v                                               │
    │  save_graph()  --> graph_data/smartrecruit_graph.graphml        │
    │  detect_communities() --> [{noeud1, noeud2}, {noeud3}, ...]     │
    └─────────────────────────────────────────────────────────────────┘

Algorithme de détection de communautés :
    greedy_modularity_communities (NetworkX natif) — choix délibéré :
    - Zéro dépendance externe (pas de python-louvain ni de leidenalg)
    - Implémentation stable et reproductible
    - Optimise la modularité Q — standard de facto pour les graphes RH
    - Limite : O(n log^2 n) — parfait pour nos ~500 noeuds max (50 CVs)

Sauvegarde :
    Format GraphML (XML) — standard industriel pour les graphes.
    Interopérable avec Gephi, Cytoscape, yEd pour la visualisation.
    Conserve tous les attributs de noeuds et d'arêtes.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import networkx as nx
from networkx.algorithms.community import greedy_modularity_communities

# --------------------------------------------------------------------------- #
#  Résolution du chemin racine                                                 #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --------------------------------------------------------------------------- #
#  Logger                                                                      #
# --------------------------------------------------------------------------- #
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Constantes                                                                  #
# --------------------------------------------------------------------------- #
DEFAULT_GRAPH_DIR  = PROJECT_ROOT / "graph_data"
DEFAULT_GRAPH_FILE = DEFAULT_GRAPH_DIR / "smartrecruit_graph.graphml"


# --------------------------------------------------------------------------- #
#  Classe KnowledgeGraphManager                                                #
# --------------------------------------------------------------------------- #
class KnowledgeGraphManager:
    """
    Gestionnaire du graphe de connaissances global SmartRecruit AI.

    Responsabilités :
        - Maintenir un graphe orienté global (fusion des sous-graphes CV)
        - Persister le graphe sur disque (GraphML) pour éviter les re-extractions
        - Exposer des métriques et statistiques du graphe
        - Détecter les communautés sémantiques via greedy modularity

    Cycle de vie typique :
        manager = KnowledgeGraphManager()
        manager.load_graph()                  # Charge si existant

        for cv in cvs:
            subgraph = extract_graph_for_cv(cv, llm)
            manager.add_subgraph(subgraph)    # Fusionne

        manager.save_graph()                  # Persiste
        communities = manager.detect_communities()

    Attributs publics :
        global_graph (nx.DiGraph) : Graphe orienté global — accès direct autorisé
                                    pour les inspections et requêtes NetworkX.
    """

    def __init__(self, graph_dir: Optional[Path] = None) -> None:
        """
        Initialise le gestionnaire avec un graphe orienté vide.

        Args:
            graph_dir: Répertoire de sauvegarde. Utilise DEFAULT_GRAPH_DIR si None.
                       Le répertoire est créé automatiquement s'il n'existe pas.
        """
        self.global_graph: nx.DiGraph = nx.DiGraph()
        self.graph_dir: Path = Path(graph_dir) if graph_dir else DEFAULT_GRAPH_DIR

        # Création du répertoire de sauvegarde
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        self.default_filepath = self.graph_dir / "smartrecruit_graph.graphml"

        logger.info(
            f"[GRAPH MANAGER] Initialise. Graphe vide. "
            f"Repertoire de sauvegarde : {self.graph_dir}"
        )

    # ── Fusion de sous-graphes ───────────────────────────────────────────────

    def add_subgraph(self, subgraph: nx.DiGraph) -> None:
        """
        Fusionne un sous-graphe CV dans le graphe global.

        Comportement de nx.compose :
            - Les noeuds identiques (même ID) sont fusionnés : leurs attributs
              sont mis à jour (le sous-graphe a la priorité sur les attributs
              conflictuels — dernière écriture gagne).
            - Les arêtes dupliquées (même source + target) sont préservées sans
              doublon grâce à la structure DiGraph.
            - Les noeuds partagés entre CVs (ex: le noeud "python" apparaissant
              dans 30 CVs) ne sont stockés qu'une seule fois dans le graphe global
              mais reçoivent toutes les arêtes qui les concernent.

        Exemple de fusion sémantique :
            G1 : alice_dupont --[MAITRISE]--> python
            G2 : hinata_sato  --[MAITRISE]--> python
            → global_graph : 3 noeuds (alice, hinata, python), 2 arêtes

        Args:
            subgraph: Graphe orienté généré par extract_graph_for_cv(). Peut être vide.

        Raises:
            TypeError: Si subgraph n'est pas un nx.DiGraph.
        """
        if not isinstance(subgraph, nx.DiGraph):
            raise TypeError(
                f"[GRAPH MANAGER] add_subgraph() attend un nx.DiGraph, "
                f"reçu : {type(subgraph).__name__}"
            )

        if subgraph.number_of_nodes() == 0:
            logger.debug("[GRAPH MANAGER] Sous-graphe vide ignoré.")
            return

        before_nodes = self.global_graph.number_of_nodes()
        before_edges = self.global_graph.number_of_edges()

        # nx.compose retourne un NOUVEAU graphe — on réassigne self.global_graph
        self.global_graph = nx.compose(self.global_graph, subgraph)

        added_nodes = self.global_graph.number_of_nodes() - before_nodes
        added_edges = self.global_graph.number_of_edges() - before_edges

        logger.debug(
            f"[GRAPH MANAGER] Fusion : +{added_nodes} noeuds, +{added_edges} aretes. "
            f"Total : {self.global_graph.number_of_nodes()} noeuds, "
            f"{self.global_graph.number_of_edges()} aretes."
        )

    def add_subgraphs(self, subgraphs: list[nx.DiGraph]) -> None:
        """
        Fusionne une liste de sous-graphes en un seul appel.

        Équivalent à appeler add_subgraph() en boucle, mais logge un résumé
        global plutôt que des logs individuels.

        Args:
            subgraphs: Liste de DiGraphs. Les entrées None et graphes vides sont ignorés.
        """
        valid = [g for g in subgraphs if isinstance(g, nx.DiGraph) and g.number_of_nodes() > 0]
        logger.info(f"[GRAPH MANAGER] Fusion de {len(valid)}/{len(subgraphs)} sous-graphes valides.")

        for g in valid:
            self.add_subgraph(g)

        logger.info(
            f"[GRAPH MANAGER] Graphe global apres fusion : "
            f"{self.global_graph.number_of_nodes()} noeuds, "
            f"{self.global_graph.number_of_edges()} aretes."
        )

    # ── Persistance ──────────────────────────────────────────────────────────

    def save_graph(self, filepath: Optional[str] = None) -> Path:
        """
        Sauvegarde le graphe global au format GraphML.

        Format GraphML (XML) — Standard industriel :
            - Conserve tous les attributs de noeuds et d'arêtes (type, label, relation)
            - Interopérable avec Gephi, Cytoscape, yEd, et la plupart des libs de graphe
            - Lisible par un humain (XML) — utile pour le debug
            - Rechargeable sans perte avec load_graph()

        Args:
            filepath: Chemin du fichier de sortie. Utilise le chemin par défaut si None.
                      Le répertoire parent est créé automatiquement.

        Returns:
            Path: Chemin absolu du fichier sauvegardé.

        Raises:
            IOError: Si l'écriture échoue.
        """
        target = Path(filepath) if filepath else self.default_filepath
        target.parent.mkdir(parents=True, exist_ok=True)

        if self.global_graph.number_of_nodes() == 0:
            logger.warning("[GRAPH MANAGER] save_graph() appelé sur un graphe vide — fichier non créé.")
            return target

        try:
            nx.write_graphml(self.global_graph, str(target))
            size_kb = target.stat().st_size / 1024
            logger.info(
                f"[GRAPH MANAGER] Graphe sauvegardé : {target} "
                f"({self.global_graph.number_of_nodes()} noeuds, "
                f"{self.global_graph.number_of_edges()} aretes, "
                f"{size_kb:.1f} Ko)"
            )
            return target
        except Exception as e:
            logger.error(f"[GRAPH MANAGER] Echec de sauvegarde : {e}")
            raise IOError(f"Impossible de sauvegarder le graphe dans '{target}' : {e}") from e

    def load_graph(self, filepath: Optional[str] = None) -> bool:
        """
        Charge un graphe GraphML depuis le disque s'il existe.

        Usage typique : vérifier si un graphe a déjà été construit lors d'une
        session précédente pour éviter de relancer toutes les extractions Groq.

        Args:
            filepath: Chemin du fichier GraphML. Utilise le chemin par défaut si None.

        Returns:
            bool: True si le graphe a été chargé, False si le fichier est absent.

        Raises:
            IOError: Si le fichier existe mais est corrompu ou illisible.
        """
        target = Path(filepath) if filepath else self.default_filepath

        if not target.exists():
            logger.info(f"[GRAPH MANAGER] Aucun graphe existant trouvé : {target}")
            return False

        try:
            loaded = nx.read_graphml(str(target))
            # read_graphml retourne un Graph non-orienté par défaut si non spécifié
            # On force la conversion en DiGraph pour garantir la cohérence
            self.global_graph = nx.DiGraph(loaded)
            logger.info(
                f"[GRAPH MANAGER] Graphe chargé depuis {target} : "
                f"{self.global_graph.number_of_nodes()} noeuds, "
                f"{self.global_graph.number_of_edges()} aretes."
            )
            return True
        except Exception as e:
            logger.error(f"[GRAPH MANAGER] Echec de chargement du graphe : {e}")
            raise IOError(f"Impossible de charger le graphe depuis '{target}' : {e}") from e

    # ── Détection de communautés ─────────────────────────────────────────────

    def detect_communities(self) -> list[set]:
        """
        Détecte les communautés sémantiques dans le graphe global.

        Algorithme : greedy_modularity_communities (Clauset-Newman-Moore, 2004)
            - Optimise la modularité Q du graphe
            - Complexité : O(n log^2 n) — scalable pour nos volumes (<1000 noeuds)
            - Aucune dépendance externe (NetworkX natif)
            - Non déterministe sur les égalités, mais stable en pratique

        Conversion DiGraph -> Graph :
            La détection de communautés nécessite un graphe NON-orienté.
            to_undirected() crée une copie temporaire — le graphe global
            orienté (self.global_graph) reste intact.

        Exemple de résultat attendu pour SmartRecruit :
            [
                {'hinata_sato', 'python', 'machine_learning', 'ml_engineer'},  # Cluster IA/Data
                {'daisuke_mori', 'fitness_coach', 'nutrition', 'strength_training'},  # Cluster Santé
                {'holly_white', 'database_administrator', 'sql', 'mongodb'},   # Cluster BDD
            ]

        Returns:
            list[set]: Liste de sets de node IDs, triée par taille décroissante.
                       Retourne [] si le graphe est trop petit (<2 noeuds).

        Raises:
            RuntimeError: Si l'algorithme de détection échoue.
        """
        n_nodes = self.global_graph.number_of_nodes()
        n_edges = self.global_graph.number_of_edges()

        if n_nodes < 2:
            logger.warning(
                f"[GRAPH MANAGER] detect_communities() : graphe trop petit "
                f"({n_nodes} noeud(s)) — retourne []."
            )
            return []

        logger.info(
            f"[GRAPH MANAGER] Détection de communautés sur "
            f"{n_nodes} noeuds / {n_edges} aretes..."
        )

        try:
            # Conversion en graphe non-orienté (copie temporaire)
            undirected = self.global_graph.to_undirected()

            # greedy_modularity_communities retourne un generateur de frozensets
            communities_raw = greedy_modularity_communities(undirected)

            # Conversion en liste de sets Python (plus ergonomique que frozenset)
            communities = [set(community) for community in communities_raw]

            # Tri par taille décroissante — les grandes communautés en premier
            communities.sort(key=len, reverse=True)

            logger.info(
                f"[GRAPH MANAGER] {len(communities)} communauté(s) détectée(s). "
                f"Tailles : {[len(c) for c in communities]}"
            )
            return communities

        except Exception as e:
            logger.error(f"[GRAPH MANAGER] Echec de détection de communautés : {e}")
            raise RuntimeError(
                f"Erreur lors de greedy_modularity_communities : {e}"
            ) from e

    # ── Statistiques et inspection ───────────────────────────────────────────

    def get_stats(self) -> dict:
        """
        Retourne les statistiques clés du graphe global.

        Returns:
            dict: {
                "nodes":         int — nombre total de noeuds,
                "edges":         int — nombre total d'arêtes,
                "node_types":    dict — distribution par type (Candidat, Competence...),
                "edge_relations":dict — distribution par type de relation,
                "density":       float — densité du graphe [0, 1],
                "is_connected":  bool — graphe non-orienté connexe,
            }
        """
        G = self.global_graph

        # Distribution des types de noeuds
        node_types: dict[str, int] = {}
        for _, attrs in G.nodes(data=True):
            t = attrs.get("type", "Unknown")
            node_types[t] = node_types.get(t, 0) + 1

        # Distribution des types de relations
        edge_relations: dict[str, int] = {}
        for _, _, attrs in G.edges(data=True):
            r = attrs.get("relation", "Unknown")
            edge_relations[r] = edge_relations.get(r, 0) + 1

        return {
            "nodes":          G.number_of_nodes(),
            "edges":          G.number_of_edges(),
            "node_types":     node_types,
            "edge_relations": edge_relations,
            "density":        round(nx.density(G), 6),
            "is_connected":   nx.is_weakly_connected(G) if G.number_of_nodes() > 0 else False,
        }

    def get_nodes_by_type(self, node_type: str) -> list[dict]:
        """
        Retourne tous les noeuds d'un type donné.

        Args:
            node_type: "Candidat" | "Competence" | "Poste" | "Entreprise"

        Returns:
            list[dict]: Liste de {"id": ..., "label": ..., "type": ...}
        """
        return [
            {"id": node_id, **attrs}
            for node_id, attrs in self.global_graph.nodes(data=True)
            if attrs.get("type") == node_type
        ]

    def get_neighbors(self, node_id: str) -> list[dict]:
        """
        Retourne les noeuds directement connectés à un noeud donné.

        Args:
            node_id: Identifiant du noeud (ex: "alice_dupont", "python").

        Returns:
            list[dict]: Liste de {"id": ..., "relation": ..., "label": ...}
        """
        if node_id not in self.global_graph:
            return []

        neighbors = []
        for _, target, attrs in self.global_graph.edges(node_id, data=True):
            target_attrs = self.global_graph.nodes.get(target, {})
            neighbors.append({
                "id":       target,
                "label":    target_attrs.get("label", target),
                "type":     target_attrs.get("type", "Unknown"),
                "relation": attrs.get("relation", "?"),
            })
        return neighbors


# --------------------------------------------------------------------------- #
#  Point d'entrée : Test standalone                                            #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 65)
    print("  SmartRecruit AI - Test graph/networkx_manager.py")
    print("=" * 65)

    # ── Initialisation ───────────────────────────────────────────────────────
    print("\n[TEST 1] Initialisation du KnowledgeGraphManager...")
    manager = KnowledgeGraphManager()
    print(f"  Graphe initial : {manager.global_graph.number_of_nodes()} noeud(s)")
    print(f"  Repertoire     : {manager.graph_dir}")

    # ── Sous-graphes factices (sans LLM) ─────────────────────────────────────
    print("\n[TEST 2] Creation et fusion de 3 sous-graphes factices...")

    # CV 1 : Data Scientist
    G1 = nx.DiGraph()
    G1.add_node("alice_dupont",      type="Candidat",    label="Alice Dupont")
    G1.add_node("python",            type="Competence",  label="Python")
    G1.add_node("machine_learning",  type="Competence",  label="Machine Learning")
    G1.add_node("data_scientist",    type="Poste",       label="Data Scientist")
    G1.add_node("datatech",          type="Entreprise",  label="DataTech")
    G1.add_edge("alice_dupont", "python",           relation="MAITRISE")
    G1.add_edge("alice_dupont", "machine_learning", relation="MAITRISE")
    G1.add_edge("alice_dupont", "data_scientist",   relation="A_TRAVAILLE_COMME")
    G1.add_edge("alice_dupont", "datatech",         relation="A_TRAVAILLE_CHEZ")

    # CV 2 : ML Engineer (partage le noeud "python" avec CV 1)
    G2 = nx.DiGraph()
    G2.add_node("hinata_sato",       type="Candidat",    label="Hinata Sato")
    G2.add_node("python",            type="Competence",  label="Python")       # Noeud partagé
    G2.add_node("tensorflow",        type="Competence",  label="TensorFlow")
    G2.add_node("ml_engineer",       type="Poste",       label="ML Engineer")
    G2.add_node("ai_labs",           type="Entreprise",  label="AI Labs")
    G2.add_edge("hinata_sato", "python",      relation="MAITRISE")
    G2.add_edge("hinata_sato", "tensorflow",  relation="MAITRISE")
    G2.add_edge("hinata_sato", "ml_engineer", relation="A_TRAVAILLE_COMME")
    G2.add_edge("hinata_sato", "ai_labs",     relation="A_TRAVAILLE_CHEZ")

    # CV 3 : Fitness Coach (cluster différent)
    G3 = nx.DiGraph()
    G3.add_node("daisuke_mori",      type="Candidat",    label="Daisuke Mori")
    G3.add_node("nutrition",         type="Competence",  label="Nutrition")
    G3.add_node("fitness_coaching",  type="Competence",  label="Fitness Coaching")
    G3.add_node("personal_trainer",  type="Poste",       label="Personal Trainer")
    G3.add_edge("daisuke_mori", "nutrition",        relation="MAITRISE")
    G3.add_edge("daisuke_mori", "fitness_coaching", relation="MAITRISE")
    G3.add_edge("daisuke_mori", "personal_trainer", relation="A_TRAVAILLE_COMME")

    # Fusion
    manager.add_subgraph(G1)
    manager.add_subgraph(G2)
    manager.add_subgraph(G3)

    stats = manager.get_stats()
    print(f"\n  Apres fusion de 3 sous-graphes :")
    print(f"  Noeuds totaux     : {stats['nodes']}")
    print(f"  Aretes totales    : {stats['edges']}")
    print(f"  Densite du graphe : {stats['density']}")
    print(f"  Distribution noeuds : {stats['node_types']}")
    print(f"  Distribution aretes : {stats['edge_relations']}")

    assert stats["nodes"] == 13, f"Attendu 13 noeuds (python partage), obtenu {stats['nodes']}"
    print("\n  OK - Noeud 'python' partage correctement entre Alice et Hinata")

    # ── Voisins d'un noeud ───────────────────────────────────────────────────
    print("\n[TEST 3] Voisins du noeud 'alice_dupont' :")
    neighbors = manager.get_neighbors("alice_dupont")
    for n in neighbors:
        print(f"  --[{n['relation']}]--> {n['label']} ({n['type']})")

    # ── Noeuds par type ──────────────────────────────────────────────────────
    print("\n[TEST 4] Tous les noeuds de type 'Competence' :")
    competences = manager.get_nodes_by_type("Competence")
    for c in competences:
        print(f"  - {c['label']}")

    # ── Sauvegarde ───────────────────────────────────────────────────────────
    print("\n[TEST 5] Sauvegarde du graphe (GraphML)...")
    saved_path = manager.save_graph()
    print(f"  Fichier : {saved_path}")
    assert saved_path.exists(), "ECHEC : fichier non créé"
    print("  OK - Fichier GraphML cree")

    # ── Rechargement ─────────────────────────────────────────────────────────
    print("\n[TEST 6] Rechargement depuis le fichier GraphML...")
    manager2 = KnowledgeGraphManager()
    loaded = manager2.load_graph(str(saved_path))
    assert loaded, "ECHEC : load_graph() a retourné False"
    print(f"  Graphe rechargé : {manager2.global_graph.number_of_nodes()} noeuds")
    assert manager2.global_graph.number_of_nodes() == stats["nodes"]
    print("  OK - Sauvegarde/chargement sans perte de données")

    # ── Détection de communautés ─────────────────────────────────────────────
    print("\n[TEST 7] Détection de communautés (greedy modularity)...")
    communities = manager.detect_communities()
    print(f"\n  {len(communities)} communauté(s) détectée(s) :\n")
    for i, community in enumerate(communities, 1):
        labels = [
            manager.global_graph.nodes[n].get("label", n)
            for n in community
        ]
        print(f"  Communaute #{i} ({len(community)} noeuds) : {', '.join(sorted(labels))}")

    assert len(communities) >= 1, "ECHEC : aucune communauté détectée"
    print("\n  OK - Communautés détectées")

    print(f"\n{'=' * 65}")
    print("  networkx_manager.py valide. Moteur mathematique Phase 3 pret.")
    print(f"{'=' * 65}\n")
