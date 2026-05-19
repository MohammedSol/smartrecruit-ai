"""
pages/1_Recherche.py
=====================
Moteur de Recherche Semantique GraphRAG — SmartRecruit AI (Phase 4, Etape 2).

Cette page est le coeur de l'experience recruteur : elle permet d'interroger
la base de talents en langage naturel via le pipeline Hybrid GraphRAG.

Flux technique :
    Requete recruteur (st.chat_input)
        |
        v
    get_global_search_chain().invoke(requete)
        |  Retriever hybride : ChromaDB community_insights -> MongoDB CVs
        |  Prompt : PROMPT_SYNTHESE_GLOBALE
        |  LLM    : llama-3.3-70b-versatile via Groq
        v
    Reponse Markdown (fiches candidats formatees)
        |
        v
    st.session_state -> affichage persistant entre les interactions

Gestion de l'etat (session_state) :
    - recherche_resultat  : str   — Derniere reponse LLM (survit aux rerenders)
    - derniere_requete    : str   — Derniere requete saisie (affichage UX)
    - historique_requetes : list  — Historique des recherches de la session

Lancement :
    streamlit run app.py   (depuis la racine du projet)
"""

import sys
from pathlib import Path

import streamlit as st
from ui_utils import appliquer_style_et_sidebar

# --------------------------------------------------------------------------- #
#  Configuration de la page                                                    #
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Moteur Semantique | SmartRecruit AI",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
#  Resolution du chemin racine (Streamlit execute depuis la racine)           #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --------------------------------------------------------------------------- #
#  Session State — initialisation AVANT tout rendu                            #
#  CRITIQUE : ces variables doivent exister avant les widgets Streamlit.      #
#  Sans cela, un rerender efface les resultats precedents.                    #
# --------------------------------------------------------------------------- #
if "recherche_resultat"   not in st.session_state:
    st.session_state.recherche_resultat   = None
if "derniere_requete"     not in st.session_state:
    st.session_state.derniere_requete     = ""
if "historique_requetes"  not in st.session_state:
    st.session_state.historique_requetes  = []
if "chain_initialized"    not in st.session_state:
    st.session_state.chain_initialized    = False

# CSS + sidebar standard
appliquer_style_et_sidebar()

# Sidebar — section historique (specifique a cette page)
with st.sidebar:
    if st.session_state.historique_requetes:
        st.markdown(
            "<p style='font-size:0.72rem;font-weight:700;color:#6366F1;"
            "text-transform:uppercase;letter-spacing:0.08em;'>Historique</p>",
            unsafe_allow_html=True,
        )
        for req in reversed(st.session_state.historique_requetes[-8:]):
            st.markdown(
                f"<div class='hist-item'>🔍 {req[:45]}{'...' if len(req) > 45 else ''}</div>",
                unsafe_allow_html=True,
            )

    if st.session_state.historique_requetes:
        if st.button("Effacer l'historique", use_container_width=True):
            st.session_state.historique_requetes  = []
            st.session_state.recherche_resultat   = None
            st.session_state.derniere_requete     = ""
            st.rerun()


# --------------------------------------------------------------------------- #
#  Hero Header                                                                 #
# --------------------------------------------------------------------------- #
st.markdown("""
<div class="page-hero">
    <h1>Moteur <span>Semantique GraphRAG</span></h1>
    <p>
        Interrogez votre base de talents en langage naturel — francais ou anglais.
        Le moteur analyse les communautes de competences, interroge MongoDB et genere
        une synthese complete des profils les plus pertinents en quelques secondes.
    </p>
    <div>
        <span class="tip-chip">💡 "Expert Python et Data Science"</span>
        <span class="tip-chip">💡 "Ingenieur cybersecurite senior"</span>
        <span class="tip-chip">💡 "Developpeur full-stack React"</span>
    </div>
</div>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
#  Barre de recherche principale                                              #
# --------------------------------------------------------------------------- #
requete = st.chat_input(
    placeholder="Ex: Je cherche un Data Engineer expert Python et Kafka...",
    key="chat_input_recherche",
)

# --------------------------------------------------------------------------- #
#  Logique de recherche                                                        #
# --------------------------------------------------------------------------- #
if requete:
    requete = requete.strip()
    if not requete:
        st.warning("Veuillez saisir une requete.")
    else:
        # ---------------------------------------------------------------- #
        #  SPRINT A — Prompt Injection Guard                               #
        #  Import lazy + try/except : si security/ n'existe pas ou plante, #
        #  Streamlit continue normalement (degradation gracieuse).         #
        # ---------------------------------------------------------------- #
        try:
            from security.prompt_guard import scan_input
            is_safe, raison = scan_input(requete)
            if not is_safe:
                st.error(
                    f"⚠️ **Requête bloquée par le système de sécurité.**\n\n"
                    f"Motif détecté : *{raison}*\n\n"
                    "Veuillez reformuler votre recherche en langage RH naturel."
                )
                st.stop()
        except Exception:
            # Le guard est absent ou a planté → on laisse passer silencieusement
            pass
        # ---------------------------------------------------------------- #
        #  FIN Sprint A                                                     #
        # ---------------------------------------------------------------- #

        # Mise a jour de l'etat avant le spinner (survit au rerender)
        st.session_state.derniere_requete = requete

        # Ajout a l'historique (sans doublons consecutifs)
        if not st.session_state.historique_requetes or \
           st.session_state.historique_requetes[-1] != requete:
            st.session_state.historique_requetes.append(requete)

        # Execution du pipeline RAG
        with st.spinner("🧠 Interrogation du Graphe et de ChromaDB en cours..."):
            try:
                # Import lazy pour ne pas bloquer l'initialisation de la page
                from rag.chain import get_global_search_chain

                chain   = get_global_search_chain()
                reponse = chain.invoke(requete)

                if not reponse or not reponse.strip():
                    st.session_state.recherche_resultat = (
                        "_Aucun profil pertinent trouve. "
                        "Essayez une requete differente ou verifiez que "
                        "la collection `community_insights` est bien peuplee._"
                    )
                else:
                    st.session_state.recherche_resultat = reponse

            except ImportError as e:
                st.session_state.recherche_resultat = None
                st.error(
                    f"**Erreur d'import du module RAG :** `{e}`\n\n"
                    "Verifiez que les dependances sont installees :\n"
                    "```\npip install langchain langchain-groq langchain-chroma "
                    "langchain-huggingface\n```"
                )
            except Exception as e:
                err_msg = str(e)
                st.session_state.recherche_resultat = None

                if "community_insights" in err_msg or "does not exist" in err_msg.lower():
                    st.error(
                        "**Collection `community_insights` introuvable.**\n\n"
                        "Executez d'abord le pipeline GraphRAG :\n"
                        "```powershell\n"
                        "python scripts/run_graph_batch.py\n"
                        "python -m processing.community_summarizer\n"
                        "```"
                    )
                elif "GROQ_API_KEY" in err_msg or "api_key" in err_msg.lower():
                    st.error(
                        "**Cle API Groq invalide ou absente.**\n\n"
                        "Verifiez `GROQ_API_KEY` dans votre fichier `.env`."
                    )
                else:
                    st.error(f"**Erreur inattendue :** {err_msg}")


# --------------------------------------------------------------------------- #
#  Affichage des resultats                                                    #
# --------------------------------------------------------------------------- #
if st.session_state.recherche_resultat:

    # Badge de la requete active
    st.markdown(
        f"<div class='query-badge'>"
        f"🔍 <strong>Requete analysee :</strong> {st.session_state.derniere_requete}"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Message de succes
    st.success("Analyse terminee ! Voici les profils les plus pertinents.")

    # Zone de resultat stylisee
    col_result, col_actions = st.columns([3, 1])

    with col_result:
        with st.container(border=True):
            st.markdown(st.session_state.recherche_resultat.strip())

    with col_actions:
        st.markdown(
            "<p style='font-size:0.8rem;font-weight:700;color:#6366F1;"
            "text-transform:uppercase;letter-spacing:0.06em;margin-bottom:12px;'>"
            "Actions</p>",
            unsafe_allow_html=True,
        )

        # Bouton : Nouvelle recherche
        if st.button("🔄 Nouvelle recherche", use_container_width=True):
            st.session_state.recherche_resultat = None
            st.session_state.derniere_requete   = ""
            st.rerun()

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Bouton : Copier (simulation via expander)
        with st.expander("📋 Voir le texte brut"):
            st.code(st.session_state.recherche_resultat, language=None)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Info contextuelle
        st.markdown(
            "<div style='background:#F8F9FC;border:1px solid #E2E8F0;border-radius:8px;"
            "padding:14px;font-size:0.78rem;color:#64748B;line-height:1.6;'>"
            "<strong style='color:#0F172A;'>Moteur actif</strong><br>"
            "ChromaDB community_insights<br>"
            "+ MongoDB CVs complets<br>"
            "<br><strong style='color:#0F172A;'>LLM</strong><br>"
            "llama-3.3-70b-versatile<br>"
            "via Groq API"
            "</div>",
            unsafe_allow_html=True,
        )

elif not requete:
    # Etat vide — guide d'utilisation
    st.markdown("""
    <div style="text-align:center;padding:60px 20px;color:#94A3B8;">
        <div style="font-size:3rem;margin-bottom:16px;">🔍</div>
        <p style="font-size:1.1rem;font-weight:600;color:#64748B;margin-bottom:8px;">
            Commencez votre recherche
        </p>
        <p style="font-size:0.875rem;max-width:420px;margin:0 auto;line-height:1.6;">
            Saisissez votre requete dans la barre ci-dessous.<br>
            Le moteur analyse les <strong>communautes GraphRAG</strong> et les
            <strong>profils MongoDB</strong> pour vous retourner les candidats
            les plus pertinents.
        </p>
    </div>
    """, unsafe_allow_html=True)