import streamlit as st
import pymongo
from ui_utils import appliquer_style_et_sidebar
from rag.chain import get_local_chat_chain
import json
import re
from streamlit_agraph import agraph, Node, Edge, Config

# --------------------------------------------------------------------------- #
#  Configuration de la page
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Vivier Talents",
    page_icon="👥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Application du CSS global et de la Sidebar fige
appliquer_style_et_sidebar()

# --------------------------------------------------------------------------- #
#  Connexion Base de Donnees
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=300)
def fetch_candidats_from_mongo():
    """
    Se connecte a MongoDB, recupere les profils et les transforme en texte pour le RAG.
    """
    try:
        client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
        # On utilise les noms exacts vus dans MongoDB Compass
        db = client["smartrecruit"] 
        collection = db["cvs"] 
        
        candidats_db = {}
        
        for doc in collection.find():
            # 1. On cible la bonne clé pour le nom ("name")
            nom = doc.get("name", "Candidat Inconnu")
            
            # 2. On nettoie le document pour l'IA (on enleve l'_id technique)
            doc.pop("_id", None)
            
            # 3. On convertit tout le document structuré en un seul grand texte JSON
            cv_text = json.dumps(doc, ensure_ascii=False, default=str)
            
            # On ajoute au vivier
            if nom != "Candidat Inconnu" and cv_text:
                candidats_db[nom] = cv_text
                
        return candidats_db
    
    except Exception as e:
        st.error(f"Erreur de connexion a MongoDB : {e}")
        return {}

# --------------------------------------------------------------------------- #
#  Fonction de traduction (LLM)
# --------------------------------------------------------------------------- #
from rag.chain import _llm
from langchain_core.messages import HumanMessage

def traduire_fr(texte):
    if not texte: return ""
    try:
        rep = _llm.invoke([HumanMessage(content=f"Traduis ce court texte en français professionnel (contexte RH/Recrutement). Ne retourne QUE la traduction exacte, sans introduction ni commentaire : {texte}")])
        return rep.content.strip()
    except:
        return texte

# --------------------------------------------------------------------------- #
#  Layout Principal
# --------------------------------------------------------------------------- #
st.markdown("<h1>👥 Vivier Talents & Analyse</h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#64748B;'>Analysez en profondeur le profil de vos candidats grace a l'assistant RH local.</p>", unsafe_allow_html=True)

candidats_db = fetch_candidats_from_mongo()

if not candidats_db:
    st.warning("Aucun candidat trouve dans la base de donnees MongoDB.")
    st.stop()

tab1, tab2 = st.tabs(["🌐 Cartographie du Vivier", "👤 Analyse Individuelle"])

with tab1:
    st.markdown("### 🌐 Graphe des Compétences du Vivier")
    nodes = []
    edges = []
    skills_set = set()

    for nom, cv_texte in candidats_db.items():
        if not nom or nom == "Candidat Inconnu":
            continue
            
        try:
            profil_dict = json.loads(cv_texte)
            
            # 1. On ajoute TOUJOURS le candidat (On sécurise l'affichage minimum)
            nodes.append(Node(id=nom, label=nom, size=25, color="#6366F1"))
            
            # 2. Recherche flexible de la clé des compétences (Smart Search)
            raw_skills = None
            for key, value in profil_dict.items():
                # On cherche 'skills', 'Skills', 'competences', etc.
                if key.lower() in ['skills', 'compétences', 'competences']:
                    raw_skills = value
                    break
            
            # 3. Normalisation
            clean_skills = []
            if isinstance(raw_skills, list):
                clean_skills = [str(s).strip().title() for s in raw_skills if str(s).strip()]
            elif isinstance(raw_skills, str):
                clean_skills = [s.strip().title() for s in raw_skills.split(',') if s.strip()]
                
            # --- FALLBACK NLP BAsics ---
            if not clean_skills:
                summary = profil_dict.get('summary', '')
                if isinstance(summary, str) and summary:
                    # Recherche de "Proficient in" ou "Skilled in" suivi de compétences
                    match = re.search(r'(?:Proficient in|Skilled in)\s+([^.]+)', summary, re.IGNORECASE)
                    if match:
                        extracted = match.group(1)
                        # Sépare par des virgules ou "and"
                        raw_extracted = re.split(r',| and ', extracted)
                        clean_skills = [s.strip().title() for s in raw_extracted if s.strip()]
                        
            # Suppression des doublons
            clean_skills = list(set(clean_skills))
                
            # 4. Création des arêtes et des noeuds de compétences
            for skill in clean_skills:
                if skill not in skills_set:
                    nodes.append(Node(id=skill, label=skill, size=15, color="#10B981"))
                    skills_set.add(skill)
                # On relie le candidat à sa compétence
                edges.append(Edge(source=nom, target=skill))
                
        except json.JSONDecodeError:
            continue

    # 5. Affichage du Graphe
    if not nodes:
        st.warning("Aucun candidat valide à afficher.")
    else:
        config = Config(height=600, width="100%", directed=False, physics=True)
        agraph(nodes=nodes, edges=edges, config=config)

    # 6. L'outil de l'Architecte : Le Mode Debug
    '''with st.expander("🛠️ Mode Debug : Voir la structure JSON réelle de MongoDB"):
        st.info("Regarde ci-dessous comment s'appelle exactement la clé qui contient les compétences :")
        if candidats_db:
            premier_candidat_nom = list(candidats_db.keys())[0]
            st.json(json.loads(candidats_db[premier_candidat_nom]))'''
with tab2:
    col_gauche, col_droite = st.columns([1, 2])

    # -- Colonne Gauche : Selection du profil --
    with col_gauche:
        st.markdown("### 📋 Profils Disponibles")
        candidat_selectionne = st.selectbox(
            "Selectionnez un candidat",
            options=list(candidats_db.keys())
        )
        
        cv_texte = candidats_db[candidat_selectionne]
        
        with st.expander("📄 Fiche du Candidat", expanded=True):
            try:
                # On re-transforme le texte en dictionnaire juste pour faire un bel affichage
                profil_dict = json.loads(cv_texte)
                
                titre_brut = profil_dict.get('title', 'Non spécifié')
                summary_brut = profil_dict.get('summary', 'Aucun résumé disponible.')
                
                with st.spinner("Traduction du profil en cours..."):
                    titre_fr = traduire_fr(titre_brut) if titre_brut != 'Non spécifié' else titre_brut
                    summary_fr = traduire_fr(summary_brut) if summary_brut != 'Aucun résumé disponible.' else summary_brut
                
                st.markdown(f"**Poste :** {titre_fr}")
                st.markdown(f"**Email :** {profil_dict.get('email', 'Non renseigné')}")
                st.markdown(f"**Localisation :** {profil_dict.get('location', 'Non spécifié')}")
                
                st.divider()
                
                st.markdown("**Résumé :**")
                st.info(summary_fr)
                
                skills = profil_dict.get('skills', [])
                if skills:
                    st.markdown("**Compétences :**")
                    # Affiche les compétences comme de jolis petits badges
                    st.markdown(" · ".join([f"`{s}`" for s in skills]))
                    
            except json.JSONDecodeError:
                # Sécurité : Si le CV n'est pas un JSON parfait, on l'affiche normalement
                st.markdown(cv_texte)

    # -- Colonne Droite : Chatbot Local --
    with col_droite:
        st.markdown(f"### 💬 Assistant RH - Analyse de {candidat_selectionne}")
        
        # Gestion de l'historique par candidat
        historique_key = f"chat_history_{candidat_selectionne}"
        if historique_key not in st.session_state:
            st.session_state[historique_key] = [
                {"role": "assistant", "content": f"Bonjour ! Je suis l'assistant RH assigne au profil de **{candidat_selectionne}**. Que souhaitez-vous savoir sur ce candidat ?"}
            ]
            
        # Affichage de l'historique
        for msg in st.session_state[historique_key]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
        # Input utilisateur
        if prompt := st.chat_input(f"Posez une question sur {candidat_selectionne}..."):
            # Ajout du message utilisateur
            st.session_state[historique_key].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
                
            # Reponse IA
            with st.chat_message("assistant"):
                with st.spinner("Analyse du profil en cours..."):
                    try:
                        chain = get_local_chat_chain()
                        # On formatte l'historique pour la chain (si necessaire)
                        # La chain demande cv_texte et query
                        reponse = chain.invoke({
                            "cv_text": cv_texte,
                            "question": prompt
                        })
                        st.markdown(reponse)
                        st.session_state[historique_key].append({"role": "assistant", "content": reponse})
                    except Exception as e:
                        st.error(f"Erreur lors de l'analyse : {str(e)}")
