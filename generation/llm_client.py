"""
generation/llm_client.py
=========================
Client LLM central pour SmartRecruit AI — Phase 3 GraphRAG.

Responsabilite unique :
    Encapsuler tous les appels au LLM Groq (llama3-70b-8192) derriere
    une interface stable et robuste, independante du reste du pipeline.

Deux modes d'appel :
    - generate_text()  : reponse textuelle libre (resumes, analyses narratives)
    - extract_json()   : reponse forcee en JSON valide (extraction d'entites,
                         construction du graphe NetworkX)

Decisions d'architecture :
    - Pas de LangChain ici : appel direct au SDK Groq pour un controle total
      du format et de la gestion des erreurs.
    - Retry avec backoff exponentiel : les appels LLM peuvent echouer
      ponctuellement (rate limit, timeout reseau). 3 tentatives max.
    - GROQ_API_KEY lue exclusivement depuis config.settings (R3).

Installation :
    pip install groq

Usage :
    from generation.llm_client import GroqClient
    client = GroqClient()
    text = client.generate_text("Resume ce CV en 3 lignes.", system_prompt="Tu es un RH expert.")
    data = client.extract_json("Extrais les competences de ce CV : ...")
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------- #
#  Resolution du chemin racine                                                 #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from groq import Groq, APIConnectionError, APIStatusError, RateLimitError

from config.settings import GROQ_API_KEY, LLM_MODEL

# --------------------------------------------------------------------------- #
#  Logger                                                                      #
# --------------------------------------------------------------------------- #
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Constantes                                                                  #
# --------------------------------------------------------------------------- #
_MAX_RETRIES    = 3       # Nombre maximum de tentatives en cas d'erreur
_RETRY_DELAY_S  = 2.0    # Delai initial entre tentatives (double a chaque retry)
_MAX_TOKENS     = 4096   # Limite de tokens en sortie par appel
_TEMPERATURE    = 0.2    # Faible temperature : reponses deterministes et precises

# System prompt par defaut pour les appels generiques
_DEFAULT_SYSTEM = (
    "You are a helpful AI assistant specialized in HR and recruitment. "
    "Always respond in the same language as the user's input. "
    "Be concise, accurate, and professional."
)

# System prompt force pour les extractions JSON
_JSON_SYSTEM = (
    "You are a precise data extraction assistant. "
    "You MUST respond ONLY with valid JSON. "
    "Do NOT include any explanation, markdown, or text outside the JSON object. "
    "If you cannot extract the requested data, return an empty JSON object: {}"
)


# --------------------------------------------------------------------------- #
#  Classe GroqClient                                                           #
# --------------------------------------------------------------------------- #
class GroqClient:
    """
    Client robuste pour l'API Groq (llama3-70b-8192).

    Responsabilites :
        - Authentification via GROQ_API_KEY (config.settings)
        - Appels avec retry et backoff exponentiel
        - Mode texte libre (generate_text)
        - Mode JSON force (extract_json) — critique pour le pipeline GraphRAG

    Attributs :
        model (str) : Modele Groq utilise (configurable via LLM_MODEL dans .env)

    Example :
        >>> client = GroqClient()
        >>> resume = client.generate_text(
        ...     prompt="Resume le profil de Hinata Sato, ML Engineer.",
        ...     system_prompt="Tu es un recruteur senior."
        ... )
        >>> entities = client.extract_json(
        ...     prompt="Extrais les competences de ce CV : Python, TensorFlow, Docker..."
        ... )
        >>> print(entities)  # {"skills": ["Python", "TensorFlow", "Docker"]}
    """

    def __init__(self, model: Optional[str] = None) -> None:
        """
        Initialise le client Groq.

        Args:
            model: Modele Groq a utiliser. Si None, utilise LLM_MODEL depuis .env.
                   Ex: "llama3-70b-8192", "llama3-8b-8192", "mixtral-8x7b-32768"

        Raises:
            EnvironmentError: Si GROQ_API_KEY est absente ou vide.
            RuntimeError: Si la connexion initiale au client Groq echoue.
        """
        if not GROQ_API_KEY:
            raise EnvironmentError(
                "[GroqClient] GROQ_API_KEY est absente ou vide.\n"
                "  1. Obtenez une cle gratuite sur : https://console.groq.com\n"
                "  2. Ajoutez-la dans .env : GROQ_API_KEY=gsk_...\n"
                "  3. Relancez le script."
            )

        self.model = model or LLM_MODEL

        try:
            self._client = Groq(api_key=GROQ_API_KEY)
            logger.info(f"[GROQ] Client initialise. Modele : {self.model}")
        except Exception as e:
            raise RuntimeError(f"[GroqClient] Echec d'initialisation du client Groq : {e}") from e

    # ── Methode privee : appel API avec retry ────────────────────────────────

    def _call_api(
        self,
        prompt:        str,
        system_prompt: str,
        response_format: Optional[dict] = None,
    ) -> str:
        """
        Effectue l'appel API Groq avec gestion des erreurs et retry exponentiel.

        Args:
            prompt:          Message utilisateur.
            system_prompt:   Instruction systeme (role et contraintes du modele).
            response_format: Si {"type": "json_object"}, force la reponse en JSON.
                             Supporte nativement par Groq (equivalent au JSON mode d'OpenAI).

        Returns:
            str: Contenu textuel brut de la reponse du modele.

        Raises:
            RuntimeError: Si toutes les tentatives ont echoue.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ]

        last_error: Optional[Exception] = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                kwargs = {
                    "model":       self.model,
                    "messages":    messages,
                    "max_tokens":  _MAX_TOKENS,
                    "temperature": _TEMPERATURE,
                }
                # Le mode JSON de Groq garantit un JSON syntaxiquement valide en sortie.
                # Combine avec le system prompt _JSON_SYSTEM pour la completude semantique.
                if response_format:
                    kwargs["response_format"] = response_format

                response = self._client.chat.completions.create(**kwargs)
                content  = response.choices[0].message.content

                logger.debug(
                    f"[GROQ] Appel reussi (tentative {attempt}/{_MAX_RETRIES}). "
                    f"Tokens : {response.usage.total_tokens}"
                )
                return content.strip()

            except RateLimitError as e:
                # Rate limit atteint — attente longue avant retry
                wait = _RETRY_DELAY_S * (2 ** attempt)
                logger.warning(
                    f"[GROQ] Rate limit atteint (tentative {attempt}). "
                    f"Attente {wait:.1f}s... Detail : {e}"
                )
                last_error = e
                time.sleep(wait)

            except APIConnectionError as e:
                # Probleme reseau ou DNS
                wait = _RETRY_DELAY_S * attempt
                logger.warning(
                    f"[GROQ] Erreur de connexion (tentative {attempt}/{_MAX_RETRIES}). "
                    f"Retry dans {wait:.1f}s. Detail : {e}"
                )
                last_error = e
                time.sleep(wait)

            except APIStatusError as e:
                # Erreur HTTP (4xx, 5xx) — certaines sont retryables (503), d'autres non (401)
                if e.status_code in (500, 502, 503, 504):
                    wait = _RETRY_DELAY_S * attempt
                    logger.warning(
                        f"[GROQ] Erreur serveur {e.status_code} (tentative {attempt}). "
                        f"Retry dans {wait:.1f}s."
                    )
                    last_error = e
                    time.sleep(wait)
                else:
                    # 401 Unauthorized, 400 Bad Request : inutile de reessayer
                    logger.error(f"[GROQ] Erreur API non retryable ({e.status_code}) : {e.message}")
                    raise RuntimeError(
                        f"Erreur Groq API ({e.status_code}) : {e.message}\n"
                        f"Verifiez votre GROQ_API_KEY et les parametres de la requete."
                    ) from e

            except Exception as e:
                logger.error(f"[GROQ] Erreur inattendue (tentative {attempt}) : {e}")
                last_error = e
                time.sleep(_RETRY_DELAY_S)

        raise RuntimeError(
            f"[GroqClient] Echec apres {_MAX_RETRIES} tentatives. "
            f"Derniere erreur : {last_error}"
        )

    # ── API Publique ─────────────────────────────────────────────────────────

    def generate_text(
        self,
        prompt:        str,
        system_prompt: str = "",
    ) -> str:
        """
        Genere une reponse textuelle libre.

        Cas d'usage :
            - Resumer un CV en une phrase
            - Rediger la synthese d'une communaute de talents
            - Analyser la pertinence d'un profil pour un poste

        Args:
            prompt:        Instruction ou question en langage naturel.
            system_prompt: Role et contraintes du modele. Si vide, utilise le prompt
                           par defaut (assistant RH professionnel multilingue).

        Returns:
            str: Reponse textuelle du LLM, nettoyee des espaces superflus.

        Example:
            >>> client = GroqClient()
            >>> result = client.generate_text(
            ...     prompt="Summarize this profile: Data Analyst, 5 years, Python, SQL.",
            ...     system_prompt="You are a senior recruiter."
            ... )
            >>> print(result)
        """
        system = system_prompt.strip() if system_prompt.strip() else _DEFAULT_SYSTEM
        logger.debug(f"[GROQ] generate_text() | Modele : {self.model} | Prompt : {prompt[:80]}...")
        return self._call_api(prompt=prompt, system_prompt=system)

    def extract_json(
        self,
        prompt:        str,
        system_prompt: str = "",
    ) -> dict:
        """
        Extrait des donnees structurees depuis un texte et les retourne en dict Python.

        Mecanisme de double securite :
            1. `response_format={"type": "json_object"}` : force Groq a produire
               du JSON syntaxiquement valide (niveau protocole).
            2. `_JSON_SYSTEM` : interdit au modele d'inclure du texte hors JSON
               (niveau semantique).

        Utilisation critique :
            - Extraction d'entites et de relations depuis un CV (Phase 3 GraphRAG)
            - Format de sortie attendu par graph_builder.py :
              {"entities": [...], "relations": [...]}

        Args:
            prompt:        Texte source + instruction d'extraction.
            system_prompt: System prompt supplementaire. Sera ajoute AVANT _JSON_SYSTEM.
                           Utile pour specifier le schema JSON attendu.

        Returns:
            dict: Donnees extraites. Retourne {} si le parsing JSON echoue.

        Example:
            >>> client = GroqClient()
            >>> cv_text = "Alice Dupont, ML Engineer. Skills: Python, TensorFlow. Worked at Google."
            >>> data = client.extract_json(
            ...     prompt=f"Extract entities and relations from this CV:\\n{cv_text}",
            ...     system_prompt=(
            ...         "Return a JSON with keys: "
            ...         "'entities' (list of {name, type}) and "
            ...         "'relations' (list of {source, relation, target})."
            ...     )
            ... )
            >>> print(data)
            # {"entities": [{"name": "Alice Dupont", "type": "Person"}, ...], "relations": [...]}
        """
        # Construction du system prompt : schema utilisateur + contrainte JSON obligatoire
        if system_prompt.strip():
            system = f"{system_prompt.strip()}\n\n{_JSON_SYSTEM}"
        else:
            system = _JSON_SYSTEM

        logger.debug(f"[GROQ] extract_json() | Modele : {self.model} | Prompt : {prompt[:80]}...")

        raw = self._call_api(
            prompt=prompt,
            system_prompt=system,
            response_format={"type": "json_object"},
        )

        # Parsing avec fallback securise
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(
                f"[GROQ] JSONDecodeError malgre le mode JSON force. "
                f"Reponse brute : '{raw[:200]}'. Erreur : {e}"
            )
            return {}

    def list_available_models(self) -> list[str]:
        """
        Retourne la liste des modeles disponibles sur le compte Groq.

        Returns:
            list[str]: Noms des modeles disponibles.
        """
        try:
            models = self._client.models.list()
            return [m.id for m in models.data]
        except Exception as e:
            logger.warning(f"[GROQ] Impossible de lister les modeles : {e}")
            return []


# --------------------------------------------------------------------------- #
#  Test standalone                                                             #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 65)
    print("  SmartRecruit AI - Test generation/llm_client.py")
    print("=" * 65)

    # ── Initialisation ───────────────────────────────────────────────────────
    print("\n[TEST 1] Initialisation du GroqClient...")
    try:
        client = GroqClient()
        print(f"  Modele actif : {client.model}")
    except EnvironmentError as e:
        print(f"\n  ECHEC : {e}")
        sys.exit(1)

    # ── Liste des modeles ────────────────────────────────────────────────────
    print("\n[TEST 2] Modeles disponibles sur ce compte Groq...")
    models = client.list_available_models()
    if models:
        for m in sorted(models):
            print(f"  - {m}")
    else:
        print("  (Impossible de recuperer la liste)")

    # ── generate_text() ──────────────────────────────────────────────────────
    print("\n[TEST 3] generate_text() — Resume de profil...")
    sample_cv = (
        "Hinata Sato, Machine Learning Engineer, 6 years of experience. "
        "Skills: Python, TensorFlow, PyTorch, Kubernetes, MLflow. "
        "Worked at DataCorp (lead ML), then at AI Labs (research engineer). "
        "Master's degree in Computer Science from Tokyo University."
    )
    prompt_text = f"Summarize this candidate profile in 2 sentences for a recruiter:\n\n{sample_cv}"
    result = client.generate_text(
        prompt=prompt_text,
        system_prompt="You are a senior technical recruiter. Be concise and precise.",
    )
    print(f"\n  Reponse LLM :\n  {result}\n")
    assert isinstance(result, str) and len(result) > 10, "ECHEC : reponse trop courte"
    print("  OK - generate_text() valide")

    # ── extract_json() ───────────────────────────────────────────────────────
    print("\n[TEST 4] extract_json() — Extraction d'entites...")
    schema_hint = (
        "Return a JSON object with exactly two keys:\n"
        "  'entities': list of objects {name: str, type: 'Person'|'Skill'|'Company'|'Degree'}\n"
        "  'relations': list of objects {source: str, relation: str, target: str}\n"
        "Example relation: {source: 'Alice', relation: 'has_skill', target: 'Python'}"
    )
    prompt_json = f"Extract entities and relations from this CV text:\n\n{sample_cv}"
    data = client.extract_json(prompt=prompt_json, system_prompt=schema_hint)

    print(f"\n  Reponse JSON brute :")
    print(f"  Cles retournees : {list(data.keys())}")

    entities  = data.get("entities", [])
    relations = data.get("relations", [])
    print(f"  Entites   : {len(entities)}")
    print(f"  Relations : {len(relations)}")

    if entities:
        print(f"\n  Exemple d'entite  : {entities[0]}")
    if relations:
        print(f"  Exemple de relation : {relations[0]}")

    assert isinstance(data, dict), "ECHEC : la reponse n'est pas un dict"
    assert "entities" in data,    "ECHEC : cle 'entities' absente"
    print("\n  OK - extract_json() valide")

    print(f"\n{'=' * 65}")
    print("  llm_client.py valide. Foundation IA Phase 3 prete.")
    print(f"{'=' * 65}\n")
