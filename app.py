"""
app.py
=======
Dashboard d'accueil — SmartRecruit AI (Phase 4, Etape 1).

Portail B2B SaaS de recrutement propulse par un moteur Hybrid GraphRAG.
Architecture Streamlit native Multipage :
    app.py                       <- CE FICHIER (Dashboard & KPIs)
    interface/pages/1_Recherche.py  <- Moteur de recherche semantique
    interface/pages/2_Vivier.py     <- Pipeline Kanban candidats
    interface/pages/3_Postes.py     <- Fiches de poste & matching

Lancement :
    streamlit run app.py
"""

import sys
from pathlib import Path

import streamlit as st
from ui_utils import appliquer_style_et_sidebar

# --------------------------------------------------------------------------- #
#  Configuration globale de la page (DOIT etre le premier appel Streamlit)   #
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="SmartRecruit AI | Portail RH",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help":    "https://github.com",
        "Report a bug": None,
        "About":       "SmartRecruit AI — Plateforme RH propulsee par Hybrid GraphRAG",
    },
)

# --------------------------------------------------------------------------- #
#  Session State                                                               #
# --------------------------------------------------------------------------- #
if "initialized" not in st.session_state:
    st.session_state.initialized   = True
    st.session_state.search_query  = ""
    st.session_state.selected_cv   = None
    st.session_state.chat_history  = []

appliquer_style_et_sidebar()


# --------------------------------------------------------------------------- #
#  Hero Header                                                                 #
# --------------------------------------------------------------------------- #
st.markdown("""
<div class="hero-container">
    <div class="hero-pill">✨ Propulse par Hybrid GraphRAG</div>
    <h1 class="hero-title">
        Recrutez plus vite,<br>recrutez <span>plus intelligemment</span>.
    </h1>
    <p class="hero-subtitle">
        SmartRecruit AI connecte votre base de talents a un moteur de recherche semantique
        et a un graphe de connaissances pour vous proposer les meilleurs profils
        en langage naturel — en moins de 2 secondes.
    </p>
</div>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
#  Section 1 — KPIs Globaux                                                   #
# --------------------------------------------------------------------------- #
st.markdown('<p class="section-label">Vue d\'ensemble</p>', unsafe_allow_html=True)
st.markdown('<p class="section-title">Tableau de bord</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="section-subtitle">Metriques en temps reel de votre pipeline de recrutement.</p>',
    unsafe_allow_html=True,
)

kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)

with kpi_col1:
    st.markdown("""
    <div class="kpi-card">
        <span class="kpi-icon">👥</span>
        <div class="kpi-value">50</div>
        <div class="kpi-label">Talents Indexes</div>
        <div class="kpi-delta">↑ +50 ce mois</div>
    </div>
    """, unsafe_allow_html=True)

with kpi_col2:
    st.markdown("""
    <div class="kpi-card">
        <span class="kpi-icon">🕸️</span>
        <div class="kpi-value">15</div>
        <div class="kpi-label">Communautes Graphe</div>
        <div class="kpi-delta">Detectees automatiquement</div>
    </div>
    """, unsafe_allow_html=True)

with kpi_col3:
    st.markdown("""
    <div class="kpi-card">
        <span class="kpi-icon">⚡</span>
        <div class="kpi-value">&lt; 1.5s</div>
        <div class="kpi-label">Temps de Matching</div>
        <div class="kpi-delta">Median sur 50 requetes</div>
    </div>
    """, unsafe_allow_html=True)

with kpi_col4:
    st.markdown("""
    <div class="kpi-card">
        <span class="kpi-icon">📋</span>
        <div class="kpi-value">3</div>
        <div class="kpi-label">Postes Ouverts</div>
        <div class="kpi-delta">2 en phase finale</div>
    </div>
    """, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
#  Divider                                                                     #
# --------------------------------------------------------------------------- #
st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
#  Section 2 — Etat du systeme                                                #
# --------------------------------------------------------------------------- #
st.markdown('<p class="section-label">Infrastructure</p>', unsafe_allow_html=True)
st.markdown('<p class="section-title">Etat du Systeme</p>', unsafe_allow_html=True)

sys_col1, sys_col2 = st.columns([2, 1])

with sys_col1:
    st.markdown("""
    <div class="system-block">
        <div class="system-icon">🛰️</div>
        <div class="system-content">
            <h4>
                Moteur Hybride GraphRAG
                &nbsp;
                <span class="status-badge status-online">● En ligne</span>
            </h4>
            <p>
                Le pipeline <strong>ChromaDB + MongoDB + NetworkX</strong> est entierement operationnel.
                La collection <code>community_insights</code> est prete pour la recherche semantique globale.
                La collection <code>cv_embeddings</code> contient les vecteurs individuels des candidats (384 dimensions).
                Le modele d'embedding <strong>paraphrase-multilingual-MiniLM-L12-v2</strong> est charge en memoire.
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

with sys_col2:
    st.markdown("""
    <div class="system-block" style="flex-direction:column;gap:16px;">
        <div>
            <div style="font-size:0.72rem;font-weight:700;color:#6366F1;text-transform:uppercase;
                        letter-spacing:0.08em;margin-bottom:10px;">Composants</div>
            <div style="display:flex;flex-direction:column;gap:8px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-size:0.82rem;color:#374151;">ChromaDB</span>
                    <span class="status-badge status-online" style="font-size:0.7rem;">Actif</span>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-size:0.82rem;color:#374151;">MongoDB</span>
                    <span class="status-badge status-online" style="font-size:0.7rem;">Actif</span>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-size:0.82rem;color:#374151;">Kafka</span>
                    <span class="status-badge status-online" style="font-size:0.7rem;">Actif</span>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-size:0.82rem;color:#374151;">Groq API</span>
                    <span class="status-badge status-online" style="font-size:0.7rem;">Actif</span>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
#  Divider                                                                     #
# --------------------------------------------------------------------------- #
st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
#  Section 3 — Navigation Rapide                                              #
# --------------------------------------------------------------------------- #
st.markdown('<p class="section-label">Navigation</p>', unsafe_allow_html=True)
st.markdown('<p class="section-title">Acces Rapide</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="section-subtitle">'
    'Utilisez le menu lateral ou les cartes ci-dessous pour acceder aux modules.'
    '</p>',
    unsafe_allow_html=True,
)

nav_col1, nav_col2, nav_col3 = st.columns(3)

with nav_col1:
    st.markdown("""
    <div class="nav-card">
        <h3>🔍 Recherche IA</h3>
        <p>
            Interrogez votre base de talents en langage naturel.
            Le moteur GraphRAG analyse les communautes semantiques et remonte
            les meilleurs profils avec explication du matching.
        </p>
        <span class="nav-tag">GraphRAG</span>
        <span class="nav-tag">Semantique</span>
        <span class="nav-tag">LLM</span>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/1_Recherche.py", label="Ouvrir le moteur de recherche →", icon="🔍")

with nav_col2:
    st.markdown("""
    <div class="nav-card" style="border-left-color: #10B981;">
        <h3>👥 Vivier Talents</h3>
        <p>
            Explorez l'ensemble de vos candidats indexes. Filtrez par competence,
            localisation ou communaute graphe. Accedez aux profils complets
            et dialoguez avec l'assistant IA par candidat.
        </p>
        <span class="nav-tag" style="background:#D1FAE5;color:#065F46;">Pipeline</span>
        <span class="nav-tag" style="background:#D1FAE5;color:#065F46;">Profils</span>
        <span class="nav-tag" style="background:#D1FAE5;color:#065F46;">Chatbot</span>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/2_Vivier.py", label="Explorer le vivier →", icon="👥")

with nav_col3:
    st.markdown("""
    <div class="nav-card" style="border-left-color: #F59E0B;">
        <h3>📋 Fiches de Poste</h3>
        <p>
            Gerez vos offres d'emploi ouvertes et lancez un matching automatique
            contre toute votre base de talents pour identifier les candidats
            les plus pertinents instantanement.
        </p>
        <span class="nav-tag" style="background:#FEF3C7;color:#92400E;">Matching</span>
        <span class="nav-tag" style="background:#FEF3C7;color:#92400E;">Offres</span>
        <span class="nav-tag" style="background:#FEF3C7;color:#92400E;">Score</span>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/3_Postes.py", label="Gerer les postes →", icon="📋")


# --------------------------------------------------------------------------- #
#  Footer                                                                      #
# --------------------------------------------------------------------------- #
st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
st.markdown("""
<div style="text-align:center;padding:8px 0 24px;">
    <span style="font-size:0.78rem;color:#94A3B8;">
        SmartRecruit AI &nbsp;·&nbsp; Projet de Fin d'Etudes &nbsp;·&nbsp;
        Propulse par <strong style="color:#6366F1;">Hybrid GraphRAG</strong> &nbsp;·&nbsp;
        Groq · ChromaDB · NetworkX · MongoDB
    </span>
</div>
""", unsafe_allow_html=True)
