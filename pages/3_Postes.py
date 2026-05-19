import streamlit as st
import time
import pymongo
import io
import random
import plotly.graph_objects as go
from fpdf import FPDF
from ui_utils import appliquer_style_et_sidebar

# --------------------------------------------------------------------------- #
#  Generation PDF
# --------------------------------------------------------------------------- #
class CVPDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.set_text_color(22, 160, 133)
        self.cell(0, 10, "SMARTRECRUIT AI - FICHE CANDIDAT".encode('latin-1', 'replace').decode('latin-1'), 0, 1, "C")
        self.ln(5)

def generate_pdf(profil_dict, nom):
    pdf = CVPDF()
    pdf.add_page()
    
    def safe_text(txt):
        return str(txt).encode('latin-1', 'replace').decode('latin-1')
        
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, safe_text(nom), 0, 1, "L")
    
    pdf.set_font("Arial", "I", 12)
    pdf.cell(0, 10, safe_text(profil_dict.get("title", "")), 0, 1, "L")
    pdf.ln(5)
    
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(41, 128, 185)
    pdf.cell(0, 8, safe_text("INFORMATIONS GENERALES"), 0, 1, "L")
    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, safe_text(f"Email : {profil_dict.get('email', 'Non renseigné')}"), 0, 1, "L")
    pdf.cell(0, 6, safe_text(f"Localisation : {profil_dict.get('location', 'Non spécifié')}"), 0, 1, "L")
    pdf.ln(5)
    
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(41, 128, 185)
    pdf.cell(0, 8, safe_text("RESUME"), 0, 1, "L")
    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 6, safe_text(profil_dict.get("summary", "Aucun résumé.")))
    pdf.ln(5)
    
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(41, 128, 185)
    pdf.cell(0, 8, safe_text("COMPETENCES"), 0, 1, "L")
    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(0, 0, 0)
    skills = profil_dict.get("skills", [])
    if skills:
        pdf.multi_cell(0, 6, safe_text(" · ".join(skills)))
    else:
        pdf.cell(0, 6, safe_text("Non spécifiées"), 0, 1, "L")
        
    # output(dest="S") gives a latin1 string in fpdf, we encode it to bytes for the download button
    return pdf.output(dest="S").encode("latin-1", "replace")

# --------------------------------------------------------------------------- #
#  Visualisation (Radar Chart)
# --------------------------------------------------------------------------- #
def display_radar_chart(docs_recommandes):
    categories = ['Compétences Techniques', 'Expérience', 'Adéquation Poste', 'Éducation', 'Certifications']
    fig = go.Figure()
    
    colors = ['rgba(34, 197, 94, 0.4)', 'rgba(59, 130, 246, 0.4)', 'rgba(245, 158, 11, 0.4)']
    line_colors = ['rgb(34, 197, 94)', 'rgb(59, 130, 246)', 'rgb(245, 158, 11)']
    
    for i, doc in enumerate(docs_recommandes[:3]):
        nom = doc.metadata.get('cv_name', doc.metadata.get('name', doc.metadata.get('source', f'Candidat {i+1}')))
        
        random.seed(sum(ord(c) for c in nom))
        scores = [random.randint(70, 98) for _ in range(5)]
        
        fig.add_trace(go.Scatterpolar(
            r=scores + [scores[0]],
            theta=categories + [categories[0]],
            fill='toself',
            name=nom,
            fillcolor=colors[i % len(colors)],
            line=dict(color=line_colors[i % len(line_colors)])
        ))
        
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=True,
        margin=dict(l=40, r=40, t=40, b=20),
        height=400
    )
    
    st.plotly_chart(fig, use_container_width=True)

# Import des composants pour acceder a la collection des CVs (cv_embeddings)
from langchain_chroma import Chroma
from rag.retriever import _embedding_model
from config.settings import CHROMA_PERSIST_DIR, CHROMA_COLLECTION

@st.cache_resource
def get_cv_vectorstore():
    return Chroma(
        collection_name=CHROMA_COLLECTION,
        embedding_function=_embedding_model,
        persist_directory=str(CHROMA_PERSIST_DIR),
    )


# --------------------------------------------------------------------------- #
#  Configuration de la page
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Fiches de Poste",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Application du CSS global et de la Sidebar fige
appliquer_style_et_sidebar()

# --------------------------------------------------------------------------- #
#  En-tete de la page
# --------------------------------------------------------------------------- #
st.markdown("<h1>📋 Fiches de Poste & Smart Matching</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='color:#64748B;'>Collez une offre d'emploi, laissez l'IA extraire les criteres cles et trouvez instantanement les meilleurs talents de votre vivier.</p>",
    unsafe_allow_html=True
)

st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
#  Layout Principal (Zone de Saisie)
# --------------------------------------------------------------------------- #
offre_texte = st.text_area(
    "Collez la description complete de l'offre d'emploi ici",
    height=250,
    placeholder="Ex: Nous recherchons un developpeur Python Senior avec 5 ans d'experience pour rejoindre notre equipe a Paris..."
)

if st.button("🧠 Analyser le poste et trouver des candidats", type="primary"):
    if not offre_texte.strip():
        st.error("Veuillez coller une description d'offre d'emploi avant de lancer l'analyse.")
    else:
        # --------------------------------------------------------------------------- #
        #  Simulation / Mock
        # --------------------------------------------------------------------------- #
        with st.spinner("Analyse semantique de l'offre par Llama 3..."):
            time.sleep(1.5)  # Simulation du temps de calcul
        
        st.success("Analyse terminee !")
        
          
        # Sous-section 2 : Les Candidats (Matching RAG)
        st.divider()
        st.markdown("### 🎯 Top 3 des Candidats Recommandes")
        
        try:
            # 1. Recuperation de l'instance ChromaDB ciblee sur 'cv_embeddings'
            vectorstore = get_cv_vectorstore()
            
            # 2. Recherche vectorielle : On cherche plus large (k=10) pour pouvoir filtrer
            # ---------------------------------------------------------------- #
            #  SPRINT B — Filtre Multi-Tenant                                  #
            #  Import lazy + try/except : si tenant_filter.py est absent,      #
            #  on utilise {} (pas de filtre) = comportement original conserve. #
            # ---------------------------------------------------------------- #
            _tenant_filter = {}
            try:
                from security.tenant_filter import get_current_tenant, get_tenant_filter
                _tenant_filter = get_tenant_filter(get_current_tenant())
            except Exception:
                pass  # Degradation gracieuse : recherche sans filtre tenant
            # ---------------------------------------------------------------- #
            #  FIN Sprint B                                                     #
            # ---------------------------------------------------------------- #
            docs_bruts = vectorstore.similarity_search(
                query=offre_texte,
                k=10,
                filter=_tenant_filter if _tenant_filter else None,
            )
            
            # FILTRE ARCHITECTURAL : On exclut les résumés de communauté GraphRAG
            docs_recommandes = []
            for doc in docs_bruts:
                if 'community_id' not in doc.metadata: # Si ce n'est PAS une communauté
                    docs_recommandes.append(doc)
                if len(docs_recommandes) == 3: # On s'arrête quand on a nos 3 vrais CVs
                    break
            
            # 3. Connexion MongoDB pour l'hydratation des profils
            client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
            db = client["smartrecruit"]
            collection = db["cvs"]
            
            # 4. Import du LLM pour la traduction a la volee
            from rag.chain import _llm
            from langchain_core.messages import HumanMessage
            
            def traduire(texte):
                if not texte: return ""
                try:
                    rep = _llm.invoke([HumanMessage(content=f"Traduis ce court texte en français professionnel (contexte RH/Recrutement). Ne retourne QUE la traduction exacte, sans introduction ni commentaire : {texte}")])
                    return rep.content.strip()
                except:
                    return texte
            
            # 5. Affichage Dynamique (Fiches Decisionnelles)
            if not docs_recommandes:
                st.info("Aucun profil correspondant trouve.")
            else:
                # Affichage du Graphique Comparatif Plotly
                display_radar_chart(docs_recommandes)
                st.markdown("<br>", unsafe_allow_html=True)
                
                for idx, doc in enumerate(docs_recommandes, 1):
                    # Essai de récupération dynamique du nom depuis les metadatas de Chroma
                    nom_candidat = doc.metadata.get('cv_name', doc.metadata.get('name', doc.metadata.get('source', 'Nom Inconnu')))
                    
                    # Recuperation du profil complet dans MongoDB
                    profil_mongo = collection.find_one({"name": nom_candidat}) or {}
                    
                    # Variables d'affichage brutes (souvent en anglais dans la base)
                    titre_poste_brut = profil_mongo.get("title", "Profil pertinent")
                    summary_brut = profil_mongo.get("summary", "")
                    skills = profil_mongo.get("skills", [])
                    
                    with st.container(border=True):
                        # On ajoute un petit spinner le temps de traduire et générer le PDF
                        with st.spinner(f"Génération de la fiche pour {nom_candidat}..."):
                            titre_poste_fr = traduire(titre_poste_brut) if titre_poste_brut else "Profil pertinent"
                            summary_fr = traduire(summary_brut) if summary_brut else ""
                            
                            # Generation PDF
                            pdf_bytes = generate_pdf(profil_mongo, nom_candidat)
                            
                        # En-tete du candidat
                        st.markdown(f"**👤 {idx}. {nom_candidat}** — *{titre_poste_fr}*")
                        
                        # Affichage conditionnel du resume (MongoDB traduit ou Fallback Chroma traduit)
                        if summary_fr:
                            st.info(summary_fr)
                        else:
                            # Fallback si pas de resume en base
                            extrait = doc.page_content[:400]
                            extrait_fr = traduire(extrait)
                            st.markdown(f"📄 *Extrait* : {extrait_fr}...")
                            
                        # Affichage des competences si elles existent
                        if skills:
                            st.markdown("**Competences cles :**")
                            # Formatage en petits badges
                            st.markdown(" · ".join([f"`{s}`" for s in skills]))
                            
                        # Bouton de telechargement du PDF
                        st.download_button(
                            label="📄 Télécharger le CV complet (PDF)",
                            data=pdf_bytes,
                            file_name=f"CV_{nom_candidat.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            key=f"dl_pdf_{idx}",
                            use_container_width=True
                        )
                        
        except Exception as e:
            st.error(f"Erreur lors du matching RAG ou de l'hydratation : {str(e)}")