# ui_utils.py
"""
ui_utils.py
============
Composant UI centralise — Design System SmartRecruit AI.
Theme : Deep Tech & Élégance Minérale
"""

import streamlit as st

# --------------------------------------------------------------------------- #
#  CSS Global — Theme Unique et Professionnel                                 #
# --------------------------------------------------------------------------- #
_CSS_GLOBAL = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,300;14..32,400;14..32,500;14..32,600;14..32,700&family=Space+Grotesk:wght@400;500;600&display=swap');

/* Reset & base */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    font-weight: 400;
    font-size: 0.95rem;
    line-height: 1.5;
    color: #1A2C3E;
    scroll-behavior: smooth;
}

/* --- Palette unique: Deep Tech --- */
:root {
    --primary-deep: #0D1B2A;
    --primary-royal: #1B263B;
    --accent-teal: #2C7A7B;
    --accent-brass: #B8860B;
    --accent-platinum: #E8E8E8;
    --glow-blue: #4A90E2;
    --carbon-light: #F5F7FA;
    --carbon-border: #E2E8F0;
}

/* Masquage natif Streamlit */
#MainMenu, footer, .stDeployButton, [data-testid="stToolbar"] {
    display: none !important;
}
[data-testid="stSidebarNav"] { display: none !important; }

/* Sidebar unique - verre dépoli sombre */
[data-testid="stSidebar"] {
    min-width: 280px !important;
    max-width: 280px !important;
    width: 280px !important;
    background: linear-gradient(165deg, #0A1622 0%, #0F1A28 100%);
    backdrop-filter: blur(0px);
    border-right: 1px solid rgba(44, 122, 123, 0.3);
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.2);
    transform: translateX(0) !important;
    position: relative !important;
}
[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"] {
    display: none !important;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] .stMarkdown {
    color: #94A3B8 !important;
    font-size: 0.85rem;
}

[data-testid="stHeader"] {
    background: transparent !important;
    visibility: visible !important;
    display: block !important;
}

/* Fond principal - texture douce */
.stApp {
    background: linear-gradient(135deg, #F4F7FB 0%, #EDF2F9 100%);
}

/* --- Badges de statut raffinés --- */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    backdrop-filter: blur(4px);
}
.status-online {
    background: rgba(44, 122, 123, 0.12);
    color: #2C7A7B;
    border: 1px solid rgba(44, 122, 123, 0.3);
}
.status-warning {
    background: rgba(184, 134, 11, 0.12);
    color: #B8860B;
    border: 1px solid rgba(184, 134, 11, 0.3);
}

/* --- Cartes KPI - Style "Minéral Flottant" --- */
.kpi-card {
    background: rgba(255, 255, 255, 0.92);
    backdrop-filter: blur(0px);
    border-radius: 24px;
    padding: 1.6rem 1.2rem;
    border: 1px solid rgba(44, 122, 123, 0.2);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.02), 0 2px 4px rgba(0, 0, 0, 0.02);
    text-align: center;
    transition: all 0.35s cubic-bezier(0.2, 0.9, 0.4, 1.1);
    height: 100%;
    position: relative;
    overflow: hidden;
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, #2C7A7B, #B8860B, #4A90E2);
    transform: scaleX(0);
    transition: transform 0.4s ease;
}
.kpi-card:hover::before {
    transform: scaleX(1);
}
.kpi-card:hover {
    border-color: rgba(44, 122, 123, 0.4);
    box-shadow: 0 20px 30px -12px rgba(0, 0, 0, 0.12);
    transform: translateY(-3px);
}
.kpi-icon {
    font-size: 2rem;
    font-weight: 500;
    margin-bottom: 12px;
    background: linear-gradient(135deg, #2C7A7B, #4A90E2);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    display: inline-block;
}
.kpi-value {
    font-size: 2.4rem;
    font-weight: 700;
    background: linear-gradient(135deg, #0D1B2A, #1B263B);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    line-height: 1.2;
    margin-bottom: 6px;
    font-family: 'Space Grotesk', monospace;
}
.kpi-label {
    font-size: 0.7rem;
    font-weight: 600;
    color: #5B6E8C;
    text-transform: uppercase;
    letter-spacing: 0.1em;
}
.kpi-delta {
    font-size: 0.7rem;
    font-weight: 600;
    color: #2C7A7B;
    margin-top: 8px;
}

/* --- Cartes de navigation - Style "Plaque Technique" --- */
.nav-card {
    background: #FFFFFF;
    border-radius: 20px;
    padding: 1.8rem 1.5rem;
    border: 1px solid #E2E8F0;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.02);
    transition: all 0.3s ease;
    height: 100%;
    position: relative;
    overflow: hidden;
}
.nav-card::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, #2C7A7B, #B8860B);
    transform: scaleX(0);
    transform-origin: left;
    transition: transform 0.35s ease;
}
.nav-card:hover::after {
    transform: scaleX(1);
}
.nav-card:hover {
    border-color: #CBD5E1;
    box-shadow: 0 12px 24px -12px rgba(44, 122, 123, 0.2);
    transform: translateY(-2px);
}
.nav-card h3 {
    font-size: 1.15rem;
    font-weight: 700;
    color: #0D1B2A;
    margin: 0 0 10px 0;
    font-family: 'Space Grotesk', monospace;
}
.nav-card p {
    font-size: 0.85rem;
    color: #5B6E8C;
    line-height: 1.5;
    margin: 0 0 1.2rem 0;
}
.nav-tag {
    display: inline-block;
    background: linear-gradient(135deg, #F0F4F8, #E8EDF3);
    color: #2C7A7B;
    padding: 3px 12px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    margin-right: 6px;
    border: 1px solid rgba(44, 122, 123, 0.2);
}

/* --- Bloc système --- */
.system-block {
    background: rgba(255, 255, 255, 0.9);
    border-radius: 20px;
    padding: 1.5rem 1.8rem;
    border: 1px solid #E2E8F0;
    display: flex;
    align-items: flex-start;
    gap: 20px;
    transition: all 0.25s ease;
}
.system-block:hover {
    border-color: rgba(44, 122, 123, 0.3);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.04);
}
.system-icon {
    font-size: 2rem;
    font-weight: 500;
    background: linear-gradient(135deg, #2C7A7B, #4A90E2);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    flex-shrink: 0;
}
.system-content h4 {
    font-size: 1rem;
    font-weight: 700;
    color: #0D1B2A;
    margin: 0 0 6px 0;
}
.system-content p {
    font-size: 0.85rem;
    color: #5B6E8C;
    line-height: 1.5;
    margin: 0;
}

/* --- Hero header - Style "Aurore Boréale" --- */
.hero-container {
    background: linear-gradient(135deg, #0A1622 0%, #0F1A28 40%, #1B2A3A 100%);
    border-radius: 28px;
    padding: 3rem 3rem;
    margin-bottom: 2.5rem;
    position: relative;
    overflow: hidden;
    border: 1px solid rgba(44, 122, 123, 0.3);
}
.hero-container::before {
    content: '';
    position: absolute;
    top: -20%;
    right: -10%;
    width: 400px;
    height: 400px;
    background: radial-gradient(circle, rgba(44, 122, 123, 0.15) 0%, transparent 70%);
    border-radius: 50%;
}
.hero-container::after {
    content: '';
    position: absolute;
    bottom: -30%;
    left: -15%;
    width: 350px;
    height: 350px;
    background: radial-gradient(circle, rgba(184, 134, 11, 0.08) 0%, transparent 70%);
    border-radius: 50%;
}
.hero-title {
    font-size: 2.4rem;
    font-weight: 800;
    color: #FFFFFF;
    margin: 0 0 12px 0;
    line-height: 1.2;
    position: relative;
    letter-spacing: -0.02em;
}
.hero-title span {
    background: linear-gradient(90deg, #5DC9C9, #C49B3A, #7CB8F0);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
}
.hero-subtitle {
    font-size: 1rem;
    color: #94A3B8;
    max-width: 560px;
    line-height: 1.6;
    position: relative;
}
.hero-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(44, 122, 123, 0.15);
    border: 1px solid rgba(44, 122, 123, 0.35);
    border-radius: 40px;
    padding: 5px 18px;
    font-size: 0.7rem;
    font-weight: 600;
    color: #7CB8F0;
    letter-spacing: 0.05em;
    margin-bottom: 1.2rem;
    backdrop-filter: blur(4px);
}

/* --- Page hero compact --- */
.page-hero {
    background: linear-gradient(135deg, #0A1622 0%, #0F1A28 60%, #1B2A3A 100%);
    border-radius: 24px;
    padding: 2rem 2.5rem;
    margin-bottom: 2rem;
    border: 1px solid rgba(44, 122, 123, 0.2);
}
.page-hero h1 {
    font-size: 1.9rem;
    font-weight: 800;
    color: #FFFFFF;
    margin: 0 0 10px 0;
}
.page-hero h1 span {
    background: linear-gradient(90deg, #5DC9C9, #C49B3A);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
}
.page-hero p {
    font-size: 0.9rem;
    color: #94A3B8;
    max-width: 560px;
    line-height: 1.5;
}

/* --- Sections labels --- */
.section-label {
    font-size: 0.7rem;
    font-weight: 700;
    color: #2C7A7B;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    margin-bottom: 0.8rem;
}
.section-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: #0D1B2A;
    margin-bottom: 0.3rem;
    font-family: 'Space Grotesk', monospace;
}
.section-subtitle {
    font-size: 0.85rem;
    color: #5B6E8C;
    margin-bottom: 1.4rem;
}

/* --- Divider élégant --- */
.custom-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #2C7A7B 20%, #B8860B 50%, #2C7A7B 80%, transparent);
    margin: 2rem 0;
}

/* --- Métriques Streamlit --- */
[data-testid="metric-container"] {
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid #E2E8F0;
    border-radius: 20px;
    padding: 1.2rem 1rem !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02);
    transition: all 0.2s ease;
}
[data-testid="metric-container"]:hover {
    border-color: rgba(44, 122, 123, 0.3);
}

/* --- Zone de résultat --- */
.result-container {
    background: #FFFFFF;
    border-radius: 24px;
    padding: 2rem 2.2rem;
    border: 1px solid #E2E8F0;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.02);
    margin-top: 8px;
}
.result-container h2 {
    color: #0D1B2A;
    font-size: 1.15rem;
    font-weight: 700;
    border-bottom: 2px solid #2C7A7B;
    padding-bottom: 10px;
    margin-bottom: 1.2rem;
}
.result-container p,
.result-container li {
    color: #334155;
    font-size: 0.9rem;
    line-height: 1.65;
}
.result-container strong {
    color: #0D1B2A;
    font-weight: 600;
}
.result-container hr {
    border-color: #E2E8F0;
    margin: 1.4rem 0;
}

/* --- Badge requête --- */
.query-badge {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    background: linear-gradient(135deg, #F0F4F8, #E8EDF3);
    border: 1px solid rgba(44, 122, 123, 0.3);
    border-radius: 40px;
    padding: 6px 20px;
    font-size: 0.8rem;
    font-weight: 500;
    color: #2C7A7B;
    margin-bottom: 1rem;
}

/* --- Historique sidebar --- */
.hist-item {
    background: rgba(44, 122, 123, 0.08);
    border-radius: 10px;
    padding: 8px 12px;
    margin-bottom: 8px;
    font-size: 0.75rem;
    color: #A5B4FC !important;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    border-left: 2px solid #2C7A7B;
    transition: all 0.2s ease;
}
.hist-item:hover {
    background: rgba(44, 122, 123, 0.16);
    transform: translateX(4px);
}

/* --- Tip chips --- */
.tip-chip {
    display: inline-block;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 20px;
    padding: 6px 16px;
    font-size: 0.7rem;
    font-weight: 500;
    color: #94A3B8;
    margin: 0.5rem 0.25rem 0 0;
    cursor: default;
    transition: all 0.2s ease;
}
/* Info panel pour la sidebar de résultats */
.info-panel {
    background: #F8FAFE;
    border: 1px solid #E2E8F0;
    border-radius: 16px;
    padding: 16px;
    font-size: 0.75rem;
    line-height: 1.6;
}
.info-panel-title {
    font-weight: 700;
    color: #0D1B2A;
    margin-bottom: 6px;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
}
.info-panel-content {
    color: #5B6E8C;
}

.empty-state {
    text-align: center;
    padding: 64px 24px;
    background: rgba(255,255,255,0.5);
    border-radius: 24px;
    border: 1px dashed #CBD5E1;
}
.empty-state-icon {
    font-size: 3rem;
    margin-bottom: 16px;
    background: linear-gradient(135deg, #2C7A7B, #4A90E2);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    display: inline-block;
}
.empty-state-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #0D1B2A;
    margin-bottom: 8px;
}
.empty-state-text {
    font-size: 0.85rem;
    color: #5B6E8C;
    max-width: 420px;
    margin: 0 auto;
    line-height: 1.6;
}
/* Badges de compétences */
.skill-badge {
    display: inline-block;
    background: linear-gradient(135deg, #EEF2FF, #E8EDF3);
    color: #2C7A7B;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 500;
    margin: 4px 6px 4px 0;
    border: 1px solid rgba(44, 122, 123, 0.2);
    transition: all 0.2s ease;
}
.skill-badge:hover {
    border-color: #2C7A7B;
    transform: translateY(-1px);
}
.skills-container {
    margin-top: 8px;
    display: flex;
    flex-wrap: wrap;
}

/* Style des onglets Streamlit personnalisé */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background: transparent;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    font-size: 0.85rem;
    letter-spacing: 0.02em;
    color: #5B6E8C;
}
.stTabs [aria-selected="true"] {
    color: #2C7A7B;
    border-bottom-color: #2C7A7B;
}

.tip-chip:hover {
    border-color: #2C7A7B;
    color: #7CB8F0;

}
</style>
"""


def appliquer_style_et_sidebar(extra_css: str = "") -> None:
    """
    Injecte le CSS global + dessine la sidebar standard sur la page courante.
    """
    hide_st_style = """
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        [data-testid="stHeader"] {visibility: hidden;}
    """

    if extra_css:
        css_complet = _CSS_GLOBAL.replace("</style>", f"\n{hide_st_style}\n{extra_css}\n</style>")
    else:
        css_complet = _CSS_GLOBAL.replace("</style>", f"\n{hide_st_style}\n</style>")

    st.markdown(css_complet, unsafe_allow_html=True)

    # Sidebar avec style raffiné
    with st.sidebar:
        st.markdown("""
        <div style="margin-bottom: 1.5rem;">
            <span style="font-size: 1.4rem; font-weight: 700; background: linear-gradient(90deg, #5DC9C9, #C49B3A); -webkit-background-clip: text; background-clip: text; color: transparent; font-family: 'Space Grotesk', monospace;">SmartRecruit</span>
            <span style="font-size: 0.7rem; font-weight: 500; color: #5DC9C9; display: block; margin-top: 4px;">Hybrid GraphRAG Platform</span>
        </div>
        """, unsafe_allow_html=True)
        st.divider()

        st.markdown("<span style='font-size: 0.7rem; font-weight: 600; color: #5DC9C9; letter-spacing: 0.1em;'>NAVIGATION</span>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.page_link("app.py", label="Dashboard", icon="📊")
        st.page_link("pages/1_Recherche.py", label="Recherche IA", icon="🔍")
        st.page_link("pages/2_Vivier.py", label="Vivier Talents", icon="👥")
        st.page_link("pages/3_Postes.py", label="Fiches de Poste", icon="📋")

        st.divider()
        st.markdown(
            "<p style='font-size:0.7rem;color:#475569;'>"
            "Version 1.0.0-beta<br>"
            "Moteur : llama-3.3-70b-versatile<br>"
            "Pipeline : GraphRAG + ChromaDB"
            "</p>",
            unsafe_allow_html=True,
        )