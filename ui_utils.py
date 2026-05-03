"""
ui_utils.py
============
Composant UI centralise — Design System SmartRecruit AI.

Principe DRY : ce module est l'unique source de verite pour :
    - Le CSS global (typographie, masquages Streamlit, couleurs B2B)
    - La sidebar de navigation (logo, page_link, version)

Usage dans chaque page :
    from ui_utils import appliquer_style_et_sidebar
    appliquer_style_et_sidebar()          # Appel minimal
    appliquer_style_et_sidebar(extra_css) # Avec CSS additionnel specifique a la page

Architecture :
    CSS global     -> injecte une seule fois par page via st.markdown
    CSS additionnel-> CSS specifique a chaque page (result-container, page-hero, etc.)
    Sidebar        -> dessinee systematiquement avec le meme contenu sur toutes les pages
"""

import streamlit as st

# --------------------------------------------------------------------------- #
#  CSS Global — commun a toutes les pages                                     #
# --------------------------------------------------------------------------- #
_CSS_GLOBAL = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Typographie globale ─────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}

/* ── Masquages natifs Streamlit ──────────────────────────────────────── */
#MainMenu                       { display: none !important; }
footer                          { display: none !important; }

/* Navigation multipage native cachee */
[data-testid="stSidebarNav"]    { display: none !important; }

/* 1. Header transparent mais ABSOLUMENT visible */
[data-testid="stHeader"] { 
    background-color: transparent !important; 
    visibility: visible !important;
    display: block !important;
}

/* 2. On cache STRICTEMENT la zone droite (toolbar, deploy) */
[data-testid="stToolbar"] { 
    display: none !important; 
}
[data-testid="stDecoration"], [data-testid="stStatusWidget"] { 
    display: none !important; 
}

/* 3. On fige la sidebar OUVERTE (Pinning SaaS) */
[data-testid="stSidebar"] {
    min-width: 260px !important;
    max-width: 260px !important;
    transform: translateX(0) !important;
    visibility: visible !important;
    position: relative !important;
}
/* Suppression des boutons de reduction/agrandissement pour empecher l'interaction */
[data-testid="stSidebarCollapseButton"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
/* ────────────────────────────────────────────────────────────────────── */
/* ── Fond de page ────────────────────────────────────────────────────── */
.stApp { background-color: #F8F9FC; }

/* ── Sidebar ─────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%);
    border-right: 1px solid #334155;
}
[data-testid="stSidebar"] * {
    color: #CBD5E1 !important;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] p {
    color: #94A3B8 !important;
    font-size: 0.85rem;
}

/* ── Badges de statut (partages) ─────────────────────────────────────── */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
}
.status-online  { background: #D1FAE5; color: #065F46; }
.status-warning { background: #FEF3C7; color: #92400E; }

/* ── Cartes KPI (Dashboard) ──────────────────────────────────────────── */
.kpi-card {
    background: #FFFFFF;
    border-radius: 12px;
    padding: 24px 20px;
    border: 1px solid #E2E8F0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    text-align: center;
    transition: box-shadow 0.2s ease, transform 0.2s ease;
    height: 100%;
}
.kpi-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.10); transform: translateY(-2px); }
.kpi-icon   { font-size: 2rem;   margin-bottom: 8px;  display: block; }
.kpi-value  { font-size: 2.2rem; font-weight: 700; color: #0F172A; line-height: 1.1; margin-bottom: 4px; }
.kpi-label  { font-size: 0.8rem; font-weight: 500; color: #64748B; text-transform: uppercase; letter-spacing: 0.06em; }
.kpi-delta  { font-size: 0.75rem; color: #10B981; font-weight: 600; margin-top: 6px; }

/* ── Cartes de navigation (Dashboard) ───────────────────────────────── */
.nav-card {
    background: #FFFFFF;
    border-radius: 12px;
    padding: 28px 24px;
    border: 1px solid #E2E8F0;
    border-left: 4px solid #6366F1;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    transition: border-left-color 0.2s ease, box-shadow 0.2s ease;
    height: 100%;
}
.nav-card:hover { border-left-color: #4F46E5; box-shadow: 0 4px 16px rgba(99,102,241,0.12); }
.nav-card h3    { font-size: 1.05rem; font-weight: 700; color: #0F172A; margin: 0 0 8px 0; }
.nav-card p     { font-size: 0.875rem; color: #64748B; line-height: 1.5; margin: 0 0 16px 0; }
.nav-tag {
    display: inline-block;
    background: #EEF2FF; color: #4338CA;
    padding: 2px 10px; border-radius: 4px;
    font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.04em; margin-right: 4px;
}

/* ── Blocs systeme (Dashboard) ───────────────────────────────────────── */
.system-block {
    background: #FFFFFF;
    border-radius: 12px;
    padding: 24px 28px;
    border: 1px solid #E2E8F0;
    display: flex; align-items: flex-start; gap: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.system-icon             { font-size: 2.5rem; flex-shrink: 0; }
.system-content h4       { font-size: 1rem; font-weight: 700; color: #0F172A; margin: 0 0 6px 0; }
.system-content p        { font-size: 0.85rem; color: #64748B; margin: 0; line-height: 1.5; }

/* ── Hero header (commun) ────────────────────────────────────────────── */
.hero-container {
    background: linear-gradient(135deg, #0F172A 0%, #1E293B 60%, #312E81 100%);
    border-radius: 16px; padding: 48px 40px; margin-bottom: 32px;
    position: relative; overflow: hidden;
}
.hero-container::before {
    content: ""; position: absolute; top: -40%; right: -10%;
    width: 500px; height: 500px;
    background: radial-gradient(circle, rgba(99,102,241,0.2) 0%, transparent 70%);
    border-radius: 50%;
}
.hero-title      { font-size: 2.4rem; font-weight: 800; color: #FFFFFF; margin: 0 0 12px 0; line-height: 1.2; position: relative; }
.hero-title span { background: linear-gradient(90deg, #818CF8, #C4B5FD); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.hero-subtitle   { font-size: 1.05rem; color: #94A3B8; margin: 0; line-height: 1.6; max-width: 600px; position: relative; }
.hero-pill       { display: inline-flex; align-items: center; gap: 6px; background: rgba(99,102,241,0.2); border: 1px solid rgba(99,102,241,0.4); border-radius: 20px; padding: 4px 14px; font-size: 0.78rem; font-weight: 600; color: #C4B5FD; margin-bottom: 20px; position: relative; }

/* ── Page hero compact (pages internes) ──────────────────────────────── */
.page-hero { background: linear-gradient(135deg, #0F172A 0%, #1E293B 60%, #312E81 100%); border-radius: 14px; padding: 32px 36px; margin-bottom: 28px; }
.page-hero h1   { font-size: 1.9rem; font-weight: 800; color: #FFFFFF; margin: 0 0 10px 0; }
.page-hero h1 span { background: linear-gradient(90deg, #818CF8, #C4B5FD); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.page-hero p    { font-size: 0.95rem; color: #94A3B8; margin: 0; line-height: 1.6; max-width: 580px; }

/* ── Section labels (commun) ─────────────────────────────────────────── */
.section-label    { font-size: 0.72rem; font-weight: 700; color: #6366F1; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 12px; }
.section-title    { font-size: 1.3rem;  font-weight: 700; color: #0F172A; margin-bottom: 4px; }
.section-subtitle { font-size: 0.875rem; color: #64748B; margin-bottom: 20px; }

/* ── Divider (commun) ────────────────────────────────────────────────── */
.custom-divider { height: 1px; background: linear-gradient(90deg, transparent, #E2E8F0 20%, #E2E8F0 80%, transparent); margin: 32px 0; }

/* ── Metriques Streamlit (Dashboard) ────────────────────────────────── */
[data-testid="metric-container"] { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 20px !important; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }

/* ── Zone de resultat (1_Recherche) ─────────────────────────────────── */
.result-container { background: #FFFFFF; border-radius: 12px; padding: 32px 36px; border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,0.06); margin-top: 8px; }
.result-container h2    { color: #0F172A; font-size: 1.15rem; font-weight: 700; border-bottom: 2px solid #6366F1; padding-bottom: 6px; margin-bottom: 16px; }
.result-container p,
.result-container li    { color: #374151; font-size: 0.92rem; line-height: 1.65; }
.result-container strong { color: #0F172A; }
.result-container hr    { border-color: #E2E8F0; margin: 20px 0; }

/* ── Badge requete (1_Recherche) ─────────────────────────────────────── */
.query-badge { display: inline-flex; align-items: center; gap: 8px; background: #EEF2FF; border: 1px solid #C7D2FE; border-radius: 8px; padding: 8px 16px; font-size: 0.88rem; font-weight: 500; color: #3730A3; margin-bottom: 16px; }

/* ── Historique sidebar (1_Recherche) ────────────────────────────────── */
.hist-item { background: rgba(99,102,241,0.1); border-radius: 6px; padding: 6px 10px; margin-bottom: 6px; font-size: 0.78rem; color: #94A3B8 !important; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-left: 2px solid #6366F1; }

/* ── Tip chips (1_Recherche) ─────────────────────────────────────────── */
.tip-chip { display: inline-block; background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.12); border-radius: 20px; padding: 4px 12px; font-size: 0.75rem; color: #CBD5E1; margin: 8px 4px 0 0; cursor: default; }
</style>
"""


# --------------------------------------------------------------------------- #
#  Fonction publique unique                                                    #
# --------------------------------------------------------------------------- #
def appliquer_style_et_sidebar(extra_css: str = "") -> None:
    """
    Injecte le CSS global + dessine la sidebar standard sur la page courante.

    A appeler immediatement apres st.set_page_config() dans chaque page.

    Args:
        extra_css: CSS additionnel specifique a la page (optionnel).
                   Exemple : des classes utilisees uniquement dans cette page.
                   Le CSS passe ici est injecte APRES le CSS global dans le meme
                   bloc <style>, evitant un second appel HTTP.

    Example:
        # app.py
        from ui_utils import appliquer_style_et_sidebar
        st.set_page_config(...)
        appliquer_style_et_sidebar()

        # pages/2_Vivier.py — avec CSS additionnel
        from ui_utils import appliquer_style_et_sidebar
        st.set_page_config(...)
        appliquer_style_et_sidebar(extra_css=\"\"\"
            .kanban-card { border-radius: 8px; ... }
        \"\"\")
    """
    # ── Injection CSS (global + additionnel fusionne en un seul bloc) ────────
    if extra_css:
        css_complet = _CSS_GLOBAL.replace("</style>", f"\n{extra_css}\n</style>")
    else:
        css_complet = _CSS_GLOBAL

    st.markdown(css_complet, unsafe_allow_html=True)

    # ── Sidebar standard ─────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🧠 SmartRecruit AI")
        st.markdown(
            "<p style='color:#64748B;font-size:0.8rem;'>Hybrid GraphRAG Platform</p>",
            unsafe_allow_html=True,
        )
        st.divider()

        st.markdown("**Navigation**")
        st.page_link("app.py",               label="Dashboard",       icon="🏠")
        st.page_link("pages/1_Recherche.py", label="Recherche IA",    icon="🔍")
        st.page_link("pages/2_Vivier.py",    label="Vivier Talents",  icon="👥")
        st.page_link("pages/3_Postes.py",    label="Fiches de Poste", icon="📋")

        st.divider()
        st.markdown(
            "<p style='font-size:0.75rem;color:#475569;'>"
            "Version 1.0.0-beta<br>"
            "Moteur : llama-3.3-70b-versatile<br>"
            "Pipeline : GraphRAG + ChromaDB"
            "</p>",
            unsafe_allow_html=True,
        )
