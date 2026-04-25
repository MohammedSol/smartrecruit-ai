"""
scripts/prepare_kaggle_data.py
==============================
Script ETL — Lit le dataset CSV Kaggle, nettoie et normalise les données,
et exporte chaque ligne sous forme d'un fichier JSON conforme au schéma
canonique SmartRecruit AI.

Respect RGPD : Les colonnes sensibles (Age, Gender, Race, Ethnicity)
sont explicitement exclues du traitement et n'apparaissent jamais dans
les fichiers de sortie.

Usage (depuis la racine du projet, .venv activé) :
    python scripts/prepare_kaggle_data.py
"""

import json
import re
import sys
import uuid
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
#  Résolution dynamique des chemins (indépendant du répertoire de lancement)  #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV    = PROJECT_ROOT / "data" / "raw" / "dataset.csv"
OUTPUT_DIR   = PROJECT_ROOT / "data" / "sample_cvs"

# Ajoute la racine au sys.path pour permettre : from config.settings import ...
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Nombre de lignes à extraire pour les tests
N_ROWS = 50

# --------------------------------------------------------------------------- #
#  🚨 RGPD — Colonnes INTERDITES                                               #
#  Ces colonnes ne doivent JAMAIS être lues, mappées ou exportées.            #
# --------------------------------------------------------------------------- #
FORBIDDEN_COLUMNS = {"Age", "Gender", "Race", "Ethnicity"}

# --------------------------------------------------------------------------- #
#  Mapping CSV → Schéma JSON canonique SmartRecruit AI                        #
# --------------------------------------------------------------------------- #
COLUMN_MAP = {
    "Job Applicant Name": "name",
    "Job Roles":          "title",
    "Resume":             "summary",
}

# Valeurs par défaut RGPD-safe pour les champs non présents dans le CSV
DEFAULTS = {
    "email":      "non-renseigné@example.com",
    "phone":      "N/A",
    "skills":     [],        # Sera enrichi en Phase 2 (extraction NLP)
    "experience": [],        # Sera structuré en Phase 2
    "education":  [],        # Sera structuré en Phase 2
    "languages":  ["Non spécifié"],
    "location":   "Non spécifié",
}


# --------------------------------------------------------------------------- #
#  Fonctions utilitaires                                                       #
# --------------------------------------------------------------------------- #

def clean_text(text: str) -> str:
    """
    Nettoie un texte brut issu d'un CV CSV :
    - Supprime les retours à la ligne et tabulations.
    - Réduit les espaces multiples à un seul espace.
    - Retire les caractères non-ASCII ou de contrôle parasites.
    - Strip les espaces en début/fin.

    Args:
        text: Texte brut à nettoyer.

    Returns:
        str: Texte normalisé.
    """
    if not isinstance(text, str):
        return ""

    # Remplace retours chariot, tabulations et sauts de ligne par un espace
    text = re.sub(r"[\r\n\t]+", " ", text)

    # Supprime les caractères de contrôle invisibles (sauf espace standard)
    text = re.sub(r"[^\x20-\x7E\u00C0-\u024F]", " ", text)

    # Réduit les espaces multiples à un seul
    text = re.sub(r" {2,}", " ", text)

    return text.strip()


def purge_output_dir(directory: Path) -> None:
    """
    Supprime tous les fichiers .json existants dans le dossier de sortie
    pour repartir sur une base propre. Crée le dossier s'il n'existe pas.

    Args:
        directory: Chemin du dossier à purger/créer.
    """
    directory.mkdir(parents=True, exist_ok=True)

    json_files = list(directory.glob("*.json"))
    if json_files:
        print(f"🗑️  Purge de {len(json_files)} fichier(s) JSON existant(s)...")
        for f in json_files:
            f.unlink()
        print("   Dossier nettoyé.\n")
    else:
        print("📁 Dossier de sortie vide — aucune purge nécessaire.\n")


def validate_columns(df: pd.DataFrame) -> None:
    """
    Vérifie que les colonnes requises sont présentes dans le DataFrame
    et lève une erreur explicite si l'une d'elles manque.

    Args:
        df: DataFrame chargé depuis le CSV.

    Raises:
        KeyError: Si une colonne du COLUMN_MAP est absente du CSV.
    """
    missing = [col for col in COLUMN_MAP if col not in df.columns]
    if missing:
        raise KeyError(
            f"\n❌ Colonnes manquantes dans le CSV : {missing}\n"
            f"   Colonnes disponibles : {list(df.columns)}"
        )

    # Vérification RGPD : audit des colonnes interdites présentes dans le CSV
    found_forbidden = FORBIDDEN_COLUMNS.intersection(set(df.columns))
    if found_forbidden:
        print(f"🔒 RGPD — Colonnes sensibles détectées et ignorées : {found_forbidden}")


def row_to_cv(row: pd.Series, index: int) -> dict:
    """
    Convertit une ligne du DataFrame en dictionnaire conforme au schéma
    canonique SmartRecruit AI.

    Les champs RGPD (Age, Gender, Race, Ethnicity) ne sont jamais accédés.

    Args:
        row:   Ligne du DataFrame pandas.
        index: Index 1-based pour le nom du fichier et l'ID.

    Returns:
        dict: CV structuré prêt à être sérialisé en JSON.
    """
    return {
        # Identifiant unique universel — persistera de Kafka → Mongo → ChromaDB
        "id": str(uuid.uuid4()),

        # Champs mappés depuis le CSV
        "name":    str(row.get("Job Applicant Name", "Nom inconnu")).strip(),
        "title":   str(row.get("Job Roles", "Poste non spécifié")).strip(),
        "summary": clean_text(str(row.get("Resume", ""))),

        # Champs par défaut (non présents dans ce CSV)
        "email":      DEFAULTS["email"],
        "phone":      DEFAULTS["phone"],
        "skills":     DEFAULTS["skills"],
        "experience": DEFAULTS["experience"],
        "education":  DEFAULTS["education"],
        "languages":  DEFAULTS["languages"],
        "location":   DEFAULTS["location"],
    }


# --------------------------------------------------------------------------- #
#  Point d'entrée                                                              #
# --------------------------------------------------------------------------- #

def main() -> None:
    print("=" * 60)
    print("  SmartRecruit AI — ETL Kaggle Dataset")
    print("=" * 60)

    # ── Vérification de l'existence du fichier source ─────────────────────
    if not INPUT_CSV.exists():
        print(f"\n❌ Fichier introuvable : {INPUT_CSV}")
        print("   Assurez-vous que 'dataset.csv' est bien dans 'data/raw/'.")
        sys.exit(1)

    print(f"\n📂 Source      : {INPUT_CSV}")
    print(f"📁 Destination : {OUTPUT_DIR}")
    print(f"📊 Lignes max  : {N_ROWS}\n")

    # ── Lecture du CSV ─────────────────────────────────────────────────────
    print("📖 Lecture du CSV...")
    try:
        df = pd.read_csv(INPUT_CSV, encoding="utf-8")
    except UnicodeDecodeError:
        # Fallback si le CSV n'est pas encodé en UTF-8
        df = pd.read_csv(INPUT_CSV, encoding="latin-1")
        print("   ⚠️  Encodage latin-1 détecté — conversion automatique.")

    print(f"   {len(df)} lignes trouvées. Colonnes : {list(df.columns)}\n")

    # ── Validation et audit RGPD ──────────────────────────────────────────
    validate_columns(df)

    # ── Sélection des N premières lignes ──────────────────────────────────
    df = df.head(N_ROWS).reset_index(drop=True)
    print(f"✂️  Sélection des {len(df)} premières lignes.\n")

    # ── Purge du dossier de sortie ────────────────────────────────────────
    purge_output_dir(OUTPUT_DIR)

    # ── Transformation et export ──────────────────────────────────────────
    print("⚙️  Transformation et export des CVs...\n")
    exported = 0

    for i, row in df.iterrows():
        cv        = row_to_cv(row, index=i + 1)
        filename  = f"kaggle_cv_{i + 1:02d}.json"
        file_path = OUTPUT_DIR / filename

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(cv, f, ensure_ascii=False, indent=2)

        print(f"  ✅ {filename}  —  {cv['name']} | {cv['title']}")
        exported += 1

    # ── Résumé final ──────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  ✅ {exported} CVs exportés avec succès.")
    print(f"  📁 Dossier : {OUTPUT_DIR}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
