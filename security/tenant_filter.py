"""
security/tenant_filter.py
==========================
Sprint B — Isolation Multi-Tenant (Filtrage par metadonnees ChromaDB).

Principe :
    ChromaDB supporte un parametre `filter=` dans similarity_search().
    Ce filtre est applique AVANT le calcul de similarite cosinus :
    les documents d'autres tenants ne sont jamais vus par le moteur.

    En production : get_current_tenant() lirait st.session_state["user"]["tenant"]
    Pour la soutenance : valeur statique "entreprise_A" (mock).

Degradation gracieuse :
    Si ce fichier est absent ou plante, pages/3_Postes.py utilise
    un dictionnaire vide `{}` comme filtre (= pas de filtre = comportement original).

Usage :
    from security.tenant_filter import get_current_tenant, get_tenant_filter
    filtre = get_tenant_filter(get_current_tenant())
    docs = vectorstore.similarity_search(query, k=10, filter=filtre)
"""


def get_current_tenant() -> str:
    """
    Retourne l'identifiant du tenant courant.

    Production  : lire depuis st.session_state["user"]["tenant"] apres auth.
    Soutenance  : valeur statique mock "entreprise_A".

    Returns:
        str: Identifiant du tenant (ex: "entreprise_A", "entreprise_B").
    """
    # Mock statique pour la demo — simule une session authentifiee
    return "entreprise_A"


def get_tenant_filter(tenant_id: str) -> dict:
    """
    Construit le dictionnaire de filtre ChromaDB pour un tenant donne.

    ChromaDB traduit ce dict en predicat : WHERE metadata.tenant_id = tenant_id
    applique AVANT le calcul de similarite vectorielle.

    Args:
        tenant_id (str): Identifiant du tenant (depuis get_current_tenant()).

    Returns:
        dict: Filtre ChromaDB. Ex: {"tenant_id": "entreprise_A"}
              Retourner {} signifierait "pas de filtre" (tous les tenants visibles).

    Example:
        >>> get_tenant_filter("entreprise_A")
        {'tenant_id': 'entreprise_A'}
    """
    filtre = {"tenant_id": tenant_id}

    # Log d'audit — visible dans les logs du terminal Streamlit
    print(f"[TENANT] Filtre actif : {tenant_id}")

    return filtre


# --------------------------------------------------------------------------- #
#  Test autonome (python security/tenant_filter.py)                           #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    print("=" * 55)
    print("  SmartRecruit AI — Tenant Filter | Test Sprint B")
    print("=" * 55)

    tenant = get_current_tenant()
    print(f"\n  Tenant courant  : {tenant}")

    filtre = get_tenant_filter(tenant)
    print(f"  Filtre ChromaDB : {filtre}")

    # Validation
    assert tenant == "entreprise_A",           "FAIL: tenant incorrect"
    assert filtre == {"tenant_id": "entreprise_A"}, "FAIL: filtre incorrect"

    print("\n  ✅ PASS — Filtre multi-tenant valide")
    print(f"{'=' * 55}\n")
