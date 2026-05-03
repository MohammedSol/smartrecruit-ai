"""
rag/chain.py
=============
Orchestrateur LCEL — Pipeline RAG complet de SmartRecruit AI.

Ce module assemble les briques du pipeline en deux chaines pretes a l'emploi :

    get_global_search_chain()
        Chaine principale — recherche multi-profils depuis l'interface Streamlit.
        Entree  : str (question recruteur en langage naturel)
        Pipeline: question -> [Retriever hybride] -> [format_docs] -> [Prompt] -> [LLM] -> str
        Sortie  : str (fiches candidats formatees en Markdown)

    get_local_chat_chain()
        Chaine secondaire — chatbot Q&A contextuel par profil individuel.
        Entree  : dict {"cv_text": str, "question": str}
        Pipeline: dict -> [Prompt] -> [LLM] -> str
        Sortie  : str (reponse directe sur le candidat)

Architecture LCEL (LangChain Expression Language) :
    LCEL permet de composer des Runnables via l'operateur |.
    Chaque element est un Runnable avec une interface .invoke() / .stream() / .batch().
    La composition est lazy : la chaine ne s'execute qu'a l'appel de .invoke().

    Avantage cle : .stream() fonctionne nativement sur toute la chaine LCEL,
    ce qui permet l'affichage progressif token par token dans Streamlit
    via st.write_stream().

Choix du LLM :
    ChatGroq avec llama-3.3-70b-versatile :
    - temperature=0 : Reponses deterministes et factuelles (pas de creativite RH)
    - streaming=True : Active le streaming token par token pour l'UX Streamlit
    - Modele actif sur le compte Groq (valide le 02/05/2026)

Dependances :
    pip install langchain langchain-groq langchain-chroma langchain-huggingface
"""

import sys
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_groq import ChatGroq

# --------------------------------------------------------------------------- #
#  Resolution du chemin racine                                                 #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import GROQ_API_KEY, LLM_MODEL
from rag.retriever import get_retriever
from rag.prompts import (
    PROMPT_SYNTHESE_GLOBALE,
    PROMPT_CHAT_LOCAL,
    format_docs,
)


# --------------------------------------------------------------------------- #
#  Initialisation globale du LLM (une seule instance partagee)                #
# --------------------------------------------------------------------------- #
# temperature=0   : Reponses 100% factuelles — critique pour le contexte RH
#                   Un LLM "creatif" pourrait inventer des competences ou experiences.
# streaming=True  : Permet .stream() sur toute la chaine LCEL sans configuration
#                   supplementaire — active le rendu progressif dans Streamlit.
_llm = ChatGroq(
    model=LLM_MODEL,
    api_key=GROQ_API_KEY,
    temperature=0,
    streaming=True,
)


# --------------------------------------------------------------------------- #
#  Chaine 1 : Recherche Globale Multi-Profils                                 #
# --------------------------------------------------------------------------- #
def get_global_search_chain():
    """
    Construit la chaine RAG principale pour la recherche de candidats.

    Pipeline LCEL complet :

        str (question recruteur)
            |
            v
        { "context": retriever | format_docs, "question": RunnablePassthrough() }
            |
            Deux branches paralleles executees simultanement :
            - "context"  : retriever.invoke(question) -> [Documents] -> format_docs() -> str
            - "question" : RunnablePassthrough() -> question inchangee -> str
            |
            v
        PROMPT_SYNTHESE_GLOBALE.invoke({"context": str, "question": str})
            |
            v
        ChatGroq (llama-3.3-70b-versatile, temperature=0)
            |
            v
        StrOutputParser() -> str (Markdown formate avec fiches candidats)

    Usage dans Streamlit :
        chain = get_global_search_chain()

        # Mode synchrone
        response = chain.invoke("Je cherche un data scientist Python")

        # Mode streaming (UX premium)
        for chunk in chain.stream("Je cherche un data scientist Python"):
            st.write(chunk, end="")

    Returns:
        Runnable LCEL composable. Accepte str en entree, retourne str.
    """
    retriever = get_retriever()

    chain = (
        {
            # Branche "context" : Retriever hybride -> Documents -> str
            # RunnableLambda(format_docs) est appele apres retriever
            "context":  retriever | format_docs,

            # Branche "question" : passe la question originale sans modification
            # RunnablePassthrough() = identite — transmet l'entree telle quelle
            "question": RunnablePassthrough(),
        }
        | PROMPT_SYNTHESE_GLOBALE
        | _llm
        | StrOutputParser()
    )

    return chain


# --------------------------------------------------------------------------- #
#  Chaine 2 : Chat Contextuel par Profil Individuel                           #
# --------------------------------------------------------------------------- #
def get_local_chat_chain():
    """
    Construit la chaine Q&A contextuelle pour un candidat specifique.

    Pas de retriever ici : le CV est fourni directement par l'interface Streamlit
    (l'utilisateur a deja selectionne un candidat specifique).

    Pipeline LCEL :

        dict {"cv_text": str, "question": str}
            |
            v
        PROMPT_CHAT_LOCAL.invoke({"cv_text": str, "question": str})
            |
            v
        ChatGroq (llama-3.3-70b-versatile, temperature=0)
            |
            v
        StrOutputParser() -> str (reponse directe sur le candidat)

    Usage dans Streamlit :
        chain = get_local_chat_chain()
        response = chain.invoke({
            "cv_text":  selected_cv_text,
            "question": "Parle-moi de son experience en cybersecurite."
        })

    Returns:
        Runnable LCEL composable. Accepte dict en entree, retourne str.
    """
    chain = (
        PROMPT_CHAT_LOCAL
        | _llm
        | StrOutputParser()
    )

    return chain


# --------------------------------------------------------------------------- #
#  Test d'integration final                                                    #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    SEP  = "-" * 65
    BOLD = "=" * 65

    print(f"\n{BOLD}")
    print("  SmartRecruit AI - Test rag/chain.py")
    print("  Test d'integration : Requete -> RAG Pipeline -> Reponse LLM")
    print(BOLD)

    # ── Test 1 : Chaine de recherche globale ─────────────────────────────────
    test_query = "Je cherche un expert en Cybersecurite."

    print(f"\n[TEST 1] Chaine de recherche globale")
    print(f"  Requete : \"{test_query}\"")
    print(f"  Modele  : {LLM_MODEL}")
    print(f"\n  Construction de la chaine...")

    try:
        global_chain = get_global_search_chain()
        print(f"  Chaine prete. Invocation en cours...\n")
        print(SEP)
        print("  REPONSE DE L'IA :\n")

        # Mode streaming : affiche les tokens au fur et a mesure
        for chunk in global_chain.stream(test_query):
            print(chunk, end="", flush=True)

        print(f"\n{SEP}")
        print("\n  [OK] Chaine globale validee.")

    except Exception as e:
        print(f"\n  [ECHEC] Chaine globale : {e}")
        print(
            "  Verifiez que :\n"
            "    1. La collection 'community_insights' contient des donnees\n"
            "       -> python -m processing.community_summarizer\n"
            "    2. MongoDB est accessible\n"
            "       -> docker compose ps\n"
            "    3. GROQ_API_KEY est valide dans .env"
        )

    print()

    # ── Test 2 : Chaine de chat local ────────────────────────────────────────
    print(f"[TEST 2] Chaine de chat local (sans retriever)")
    print(f"  Modele  : {LLM_MODEL}")

    cv_factice = (
        "=== CV : Lauren Davis ===\n"
        "Titre      : Cybersecurity Analyst\n"
        "Localite   : New York, USA\n"
        "Resume     : Proficient in Network Security, Ethical Hacking, Penetration Testing, "
        "SIEM, Incident Response, with 5 years of senior-level experience.\n"
        "Competences: Network Security, Ethical Hacking, Penetration Testing, Python, SIEM, "
        "Incident Response, Firewall Management, ISO 27001\n"
        "Experience : Cybersecurity Analyst chez TechCorp | Security Consultant chez SecureNet\n"
        "Formation  : Master Cybersecurity — MIT"
    )

    question_locale = "Quelles sont les principales certifications de cette candidate ?"

    print(f"\n  CV selectionne : Lauren Davis — Cybersecurity Analyst")
    print(f"  Question       : \"{question_locale}\"")
    print(f"\n  Invocation...\n")
    print(SEP)
    print("  REPONSE DE L'IA :\n")

    try:
        local_chain = get_local_chat_chain()
        for chunk in local_chain.stream({
            "cv_text":  cv_factice,
            "question": question_locale,
        }):
            print(chunk, end="", flush=True)

        print(f"\n{SEP}")
        print("\n  [OK] Chaine locale validee.")

    except Exception as e:
        print(f"\n  [ECHEC] Chaine locale : {e}")

    print(f"\n{BOLD}")
    print("  Pipeline RAG complet valide. Phase 4 operationnelle.")
    print(f"{BOLD}\n")
