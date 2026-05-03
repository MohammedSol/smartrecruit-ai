"""
rag/prompts.py
===============
Templates de prompts LangChain pour le pipeline RAG de SmartRecruit AI.

Deux templates distincts couvrent les deux modes d'interrogation :

    PROMPT_SYNTHESE_GLOBALE
        Entree  : context (community insights + CVs complets) + question recruteur
        Usage   : Recherche multi-profils depuis l'interface principale
        Sortie  : Fiches candidats formatees, ultra-concises, en francais
        LLM     : llama-3.3-70b-versatile via Groq

    PROMPT_CHAT_LOCAL
        Entree  : cv_text (un seul CV complet) + question recruteur
        Usage   : Chatbot contextuel par profil (bouton "En savoir plus")
        Sortie  : Reponse directe et concise sur ce candidat uniquement
        LLM     : llama-3.3-70b-versatile via Groq

Decisions de Prompt Engineering :
    - Interdiction explicite des introductions generiques ("Voici les candidats...")
      -> Reduit le bruit et va droit a l'information utile pour le recruteur.
    - Format de sortie encode dans le prompt (Markdown avec emojis) plutot que
      dans le code -> Plus flexible, peut etre ajuste sans toucher a chain.py.
    - "Ne te base QUE sur le contexte fourni" -> Evite les hallucinations LLM
      sur des candidats inventes ou des competences non mentionnees.
    - Reponses forcees en francais -> Coherence avec l'interface Streamlit B2B.

Usage :
    from rag.prompts import PROMPT_SYNTHESE_GLOBALE, PROMPT_CHAT_LOCAL

    chain = PROMPT_SYNTHESE_GLOBALE | llm | StrOutputParser()
    response = chain.invoke({"context": docs_text, "question": "..."})
"""

from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)

# --------------------------------------------------------------------------- #
#  Template 1 — Synthese Globale (recherche multi-profils)                   #
# --------------------------------------------------------------------------- #

_SYSTEM_SYNTHESE = SystemMessagePromptTemplate.from_template(
    "Tu es l'Assistant RH Expert de SmartRecruit AI. "
    "Ton role est d'analyser les profils fournis et de les presenter au recruteur "
    "de maniere ultra-concise, professionnelle et structuree. "
    "Tu ne dois utiliser QUE les informations fournies dans le contexte. "
    "Tes reponses sont toujours en francais."
)

_HUMAN_SYNTHESE = HumanMessagePromptTemplate.from_template(
    "CONTEXTE (resumes de communautes + CVs complets) :\n"
    "{context}\n\n"
    "REQUETE DU RECRUTEUR : {question}\n\n"
    "CONSIGNES STRICTES :\n"
    "- Utilise les resumes de communautes (Community Insights) UNIQUEMENT pour "
    "comprendre le contexte global et evaluer la pertinence du matching.\n"
    "- Pour CHAQUE candidat individuel present dans le contexte, genere "
    "EXACTEMENT le format suivant, sans aucune introduction ni conclusion :\n\n"
    "**[Nom du Candidat] - [Titre du Poste]**\n\n"
    "* \U0001f3af Matching : [1 phrase courte expliquant pourquoi ce profil correspond a la requete]\n\n"
    "* \U0001f4a1 Points forts : [competence 1] · [competence 2] · [competence 3]\n\n"
    "* \U0001f4cd Localisation : [Ville ou 'Non specifie']\n\n"
    "---\n\n"
    "INTERDICTIONS ABSOLUES :\n"
    "- NE commence PAS par 'Voici les candidats', 'Bien sur', 'Certainement' "
    "ou toute autre introduction.\n"
    "- NE termine PAS par une conclusion ou une invitation a poser d'autres questions.\n"
    "- NE mentionne PAS les identifiants techniques (community_id, mongo_id, etc.).\n"
    "- NE complete PAS avec des informations que tu ne trouves pas dans le contexte.\n"
    "- Commence directement par le nom du premier candidat en gras."
)

PROMPT_SYNTHESE_GLOBALE: ChatPromptTemplate = ChatPromptTemplate.from_messages([
    _SYSTEM_SYNTHESE,
    _HUMAN_SYNTHESE,
])
"""
Template principal — recherche multi-profils.

Variables requises :
    context  (str) : Documents concatenes (community insights + CVs complets).
                     Preparer avec : format_docs(retriever.invoke(question))
    question (str) : Requete du recruteur en langage naturel.

Sortie attendue (exemple) :
    **Alice Dupont - Data Scientist**
    * Matching : Experte en Python et ML, correspond a votre besoin en analyse predictive.
    * Points forts : Python avance, Machine Learning, TensorFlow
    * Localisation : Paris
    ---
    **Hinata Sato - ML Engineer**
    ...
"""


# --------------------------------------------------------------------------- #
#  Template 2 — Chat Local (chatbot par profil individuel)                   #
# --------------------------------------------------------------------------- #

_SYSTEM_CHAT_LOCAL = SystemMessagePromptTemplate.from_template(
    "Tu es un assistant RH dedie a l'analyse d'un seul candidat. "
    "Reponds a la question du recruteur de maniere directe et concise. "
    "Ne te base QUE sur le CV fourni dans le contexte. "
    "Si l'information n'est pas dans le CV, reponds 'Information non disponible dans le CV'. "
    "Tes reponses sont toujours en francais."
)

_HUMAN_CHAT_LOCAL = HumanMessagePromptTemplate.from_template(
    "CV DU CANDIDAT :\n"
    "{cv_text}\n\n"
    "QUESTION DU RECRUTEUR : {question}"
)

PROMPT_CHAT_LOCAL: ChatPromptTemplate = ChatPromptTemplate.from_messages([
    _SYSTEM_CHAT_LOCAL,
    _HUMAN_CHAT_LOCAL,
])
"""
Template contextuel — chatbot Q&A sur un profil specifique.

Variables requises :
    cv_text  (str) : Texte complet du CV du candidat selectionne.
    question (str) : Question precise du recruteur sur ce candidat.

Sortie attendue (exemple) :
    Question : "Combien d'annees d'experience a ce candidat ?"
    Reponse  : "Selon le CV, Alice Dupont dispose de 6 ans d'experience en
                tant que Data Scientist, dont 3 ans chez DataTech en tant que
                lead ML engineer."
"""


# --------------------------------------------------------------------------- #
#  Utilitaire : formatage des Documents LangChain en texte pour le context   #
# --------------------------------------------------------------------------- #
def format_docs(docs: list) -> str:
    """
    Concatene une liste de Documents LangChain en un bloc texte unique.

    Cette fonction est le lien entre le Retriever et le PromptTemplate :
        retriever.invoke(question) -> [Document, ...]
        format_docs([Document, ...]) -> str
        PROMPT_SYNTHESE_GLOBALE.invoke({"context": str, "question": str})

    Ajoute un separateur entre chaque document pour que le LLM distingue
    clairement les sources (community insight vs CV individuel).

    Args:
        docs: Liste de Documents LangChain (depuis retriever.py).

    Returns:
        str: Texte concatene pret a etre injecte dans {context}.

    Example:
        >>> from rag.retriever import get_retriever
        >>> retriever = get_retriever()
        >>> docs = retriever.invoke("Python developer")
        >>> context = format_docs(docs)
        >>> print(context[:200])
    """
    if not docs:
        return "Aucun document pertinent trouve dans la base de connaissances."

    sections: list[str] = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "chroma").upper()
        name   = doc.metadata.get("name", f"Document #{i}")
        header = f"[Source {i} — {source} | {name}]"
        sections.append(f"{header}\n{doc.page_content}")

    return "\n\n---\n\n".join(sections)
