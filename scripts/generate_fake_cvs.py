"""
scripts/generate_fake_cvs.py
============================
Génère 50 profils CV fictifs au format JSON canonique de SmartRecruit AI.

Sortie : data/sample_cvs/cv_01.json ... cv_50.json

Usage (depuis la racine du projet, .venv activé) :
    python scripts/generate_fake_cvs.py
"""

import json
import random
import sys
from pathlib import Path

from faker import Faker

# --------------------------------------------------------------------------- #
#  Résolution dynamique des chemins                                            #
#  Le script peut être lancé depuis n'importe où tant que la racine est       #
#  détectée via __file__                                                       #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR   = PROJECT_ROOT / "data" / "sample_cvs"
N_CVS        = 50

# Faker multilingue : profils francophones + anglophones
fake_fr = Faker("fr_FR")
fake_en = Faker("en_US")
Faker.seed(42)           # Reproductibilité — mêmes données à chaque exécution
random.seed(42)

# --------------------------------------------------------------------------- #
#  Données métier — pool de compétences & titres réalistes                    #
# --------------------------------------------------------------------------- #

TITLES = [
    "Data Scientist", "Data Engineer", "ML Engineer", "IA Engineer",
    "Développeur Python", "Développeur Full Stack", "DevOps Engineer",
    "Data Analyst", "NLP Engineer", "Backend Developer",
    "Software Engineer", "Cloud Architect", "Développeur Java",
    "Responsable Data", "Computer Vision Engineer",
]

SKILLS_POOL = [
    # Langages
    "Python", "Java", "Scala", "R", "SQL", "JavaScript", "TypeScript", "C++",
    # ML / IA
    "TensorFlow", "PyTorch", "Scikit-learn", "Keras", "Hugging Face",
    "LangChain", "OpenCV", "NLTK", "SpaCy", "XGBoost",
    # Data Engineering
    "Apache Kafka", "Apache Spark", "Airflow", "dbt", "Pandas", "NumPy",
    "ETL", "Hadoop", "Flink",
    # Bases de données
    "MongoDB", "PostgreSQL", "MySQL", "Redis", "Elasticsearch",
    "ChromaDB", "Pinecone", "Neo4j",
    # Cloud & DevOps
    "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Terraform",
    "CI/CD", "GitHub Actions", "MLflow",
    # Visualisation & BI
    "Streamlit", "Power BI", "Tableau", "Plotly", "Grafana",
]

COMPANIES = [
    "TechCorp", "DataVision", "NeuralSoft", "CloudPeak", "Nexaflow",
    "Analytix", "InnovatIA", "Bytewise", "QuantumLab", "Synapse AI",
    "DataBridge", "Cognitech", "PixelMind", "Scaleway", "Capgemini",
    "Thales", "Sopra Steria", "Orange Business", "BNP Paribas Tech", "Atos",
]

ROLES = [
    "Data Scientist Junior", "Data Scientist Senior", "Lead Data Engineer",
    "ML Engineer", "Développeur Backend Python", "Développeur Full Stack",
    "DevOps Engineer", "Data Analyst", "NLP Researcher", "Cloud Engineer",
    "Software Engineer", "IA Consultant", "Architecte Data", "Tech Lead",
]

INSTITUTIONS = [
    "Université Paris-Saclay", "Sorbonne Université", "École Polytechnique",
    "CentraleSupélec", "INSA Lyon", "Télécom Paris", "ENSAE Paris",
    "Université de Bordeaux", "Université Aix-Marseille", "EPFL (Lausanne)",
    "MIT", "Stanford University", "Georgia Tech", "ETH Zürich",
    "Université de Montréal", "ENSA Marrakech", "EMSI Casablanca",
    "ESI Alger", "Université de Tunis El Manar",
]

DEGREES = [
    "Master Informatique", "Master Data Science", "Master Intelligence Artificielle",
    "Ingénieur en Informatique", "Licence Mathématiques & Informatique",
    "Master Big Data & Analytics", "Doctorat en NLP",
    "Master Machine Learning", "Bachelor Computer Science",
    "Diplôme d'Ingénieur — Systèmes Distribués",
]

LANGUAGES_POOL = [
    ["Français", "Anglais"],
    ["Français", "Anglais", "Arabe"],
    ["Anglais", "Espagnol"],
    ["Français", "Anglais", "Espagnol"],
    ["Arabe", "Français", "Anglais"],
    ["Anglais"],
    ["Français", "Anglais", "Allemand"],
]

LOCATIONS = [
    "Paris, France", "Lyon, France", "Bordeaux, France", "Toulouse, France",
    "Marseille, France", "Nantes, France", "Montréal, Canada",
    "Casablanca, Maroc", "Rabat, Maroc", "Alger, Algérie", "Tunis, Tunisie",
    "Genève, Suisse", "Bruxelles, Belgique",
]

SUMMARY_TEMPLATES = [
    "{exp} ans d'expérience en {domain}. Spécialisé(e) dans {spec}. "
    "Passionné(e) par la résolution de problèmes complexes et la mise en production de modèles IA.",

    "Ingénieur(e) {title} avec {exp} ans d'expérience. "
    "Expertise avancée en {spec} et {domain}. "
    "À l'aise aussi bien en recherche appliquée qu'en environnement de production.",

    "{exp} ans d'expérience dans le domaine {domain}. "
    "Maîtrise de {spec}. Habitué(e) aux environnements Agile et aux cycles de livraison rapides.",

    "Profil {title} orienté résultats. {exp} ans à concevoir et déployer des solutions "
    "de {domain}. Expertise reconnue en {spec}.",
]

DOMAINS = [
    "Data Science & Machine Learning", "Data Engineering & pipelines distribués",
    "NLP & Traitement du Langage Naturel", "Computer Vision & Deep Learning",
    "Cloud & Architecture Data", "BI & Analytique avancée",
    "MLOps & mise en production de modèles", "IA Générative & LLMs",
]

EXPERIENCE_DESCRIPTIONS = [
    "Conception et déploiement d'un pipeline de données en temps réel traitement +1M événements/jour.",
    "Entraînement et optimisation de modèles de classification avec amélioration de 15% du F1-score.",
    "Mise en place d'une architecture RAG pour un moteur de recherche sémantique interne.",
    "Développement d'une API REST Python (FastAPI) exposant des prédictions ML en production.",
    "Automatisation des pipelines ETL réduisant le temps de traitement de 40%.",
    "Création d'un dashboard analytique Streamlit utilisé par 50+ recruteurs.",
    "Intégration de modèles LLM (Llama, Mistral) pour la génération de rapports automatiques.",
    "Orchestration de workflows Airflow pour la synchronisation quotidienne de 10 sources de données.",
    "Implémentation d'un système de recommandation basé sur les embeddings ChromaDB.",
    "Migration d'une infrastructure on-premise vers AWS avec réduction des coûts de 30%.",
    "Contribué à des projets open-source (LangChain, Hugging Face) avec +200 GitHub stars.",
    "Formation et encadrement d'une équipe de 3 data analysts juniors.",
]


# --------------------------------------------------------------------------- #
#  Fonction de génération d'un CV                                              #
# --------------------------------------------------------------------------- #

def generate_cv(index: int) -> dict:
    """
    Génère un CV fictif unique conforme au schéma canonique SmartRecruit AI.

    Args:
        index: Numéro séquentiel du CV (1-based) pour l'identifiant unique.

    Returns:
        dict: CV structuré prêt à être sérialisé en JSON.
    """
    # Choix aléatoire de la locale pour varier les noms et téléphones
    fake = fake_fr if random.random() < 0.6 else fake_en

    title     = random.choice(TITLES)
    exp_years = random.randint(1, 12)
    domain    = random.choice(DOMAINS)
    spec      = ", ".join(random.sample(SKILLS_POOL, k=2))

    # Résumé professionnel naturel
    summary = random.choice(SUMMARY_TEMPLATES).format(
        exp=exp_years, domain=domain, spec=spec, title=title
    )

    # Compétences : entre 5 et 10 skills distincts
    skills = random.sample(SKILLS_POOL, k=random.randint(5, 10))

    # Expériences professionnelles : 1 à 3 postes
    n_exp     = random.randint(1, 3)
    end_year  = 2025
    experience = []
    for _ in range(n_exp):
        duration_years = random.randint(1, 4)
        start_year     = end_year - duration_years
        experience.append({
            "company":     random.choice(COMPANIES),
            "role":        random.choice(ROLES),
            "duration":    f"{start_year}–{end_year}",
            "description": random.choice(EXPERIENCE_DESCRIPTIONS),
        })
        end_year = start_year - random.randint(0, 1)  # éventuel gap

    # Formation : 1 à 2 diplômes
    n_edu     = random.randint(1, 2)
    grad_year = 2025 - exp_years - random.randint(0, 2)
    education = []
    for i in range(n_edu):
        education.append({
            "institution": random.choice(INSTITUTIONS),
            "degree":      random.choice(DEGREES),
            "year":        str(grad_year - i * 3),
        })

    return {
        "id":         f"cv-{index:03d}",
        "name":       fake.name(),
        "email":      fake.email(),
        "phone":      fake.phone_number(),
        "title":      title,
        "summary":    summary,
        "skills":     skills,
        "experience": experience,
        "education":  education,
        "languages":  random.choice(LANGUAGES_POOL),
        "location":   random.choice(LOCATIONS),
    }


# --------------------------------------------------------------------------- #
#  Point d'entrée                                                              #
# --------------------------------------------------------------------------- #

def main() -> None:
    # Crée le dossier de sortie s'il n'existe pas
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 Dossier de sortie : {OUTPUT_DIR}")
    print(f"⚙️  Génération de {N_CVS} CVs fictifs...\n")

    generated = 0
    for i in range(1, N_CVS + 1):
        cv   = generate_cv(i)
        path = OUTPUT_DIR / f"cv_{i:02d}.json"

        with open(path, "w", encoding="utf-8") as f:
            json.dump(cv, f, ensure_ascii=False, indent=2)

        print(f"  ✅ {path.name}  —  {cv['name']} | {cv['title']} | {cv['location']}")
        generated += 1

    print(f"\n🎉 {generated} CVs générés avec succès dans :")
    print(f"   {OUTPUT_DIR}")


if __name__ == "__main__":
    # Ajoute la racine du projet au sys.path pour les imports futurs
    # (ex: from config.settings import ...) si le script est lancé directement
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    main()
