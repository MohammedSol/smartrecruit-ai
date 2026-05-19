"""
security/encryption.py
=======================
Sprint D — Chiffrement AES-128 (Fernet) des données PII.

Fernet est un schéma de chiffrement symétrique qui garantit :
    - Confidentialité  : AES-128-CBC (les données sont illisibles sans la clé)
    - Intégrité        : HMAC-SHA256 (toute altération du token est détectée)
    - Authenticité     : la clé sert à la fois au chiffrement et à la signature

La clé est lue depuis la variable d'environnement FERNET_KEY.
Elle ne doit JAMAIS être codée en dur dans le code ni committée dans Git.

Génération d'une clé :
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Dégradation gracieuse :
    Si ce fichier est supprimé ou si FERNET_KEY est absente, les blocs
    try/except dans les pages Streamlit affichent "[DONNÉE PROTÉGÉE]"
    sans crasher l'application.

Usage :
    from security.encryption import encrypt, decrypt

    chiffre = encrypt("alice.dupont@gmail.com", fernet_key)
    # → "gAAAAABk7x..." (illisible dans MongoDB Compass)

    clair = decrypt(chiffre, fernet_key)
    # → "alice.dupont@gmail.com" (lisible dans Streamlit)
"""

import os
from cryptography.fernet import Fernet, InvalidToken


def _load_key() -> bytes | None:
    """
    Charge la clé Fernet depuis la variable d'environnement FERNET_KEY.

    Returns:
        bytes si la clé est présente et valide, None sinon.
    """
    raw = os.getenv("FERNET_KEY", "").strip()
    if not raw:
        return None
    try:
        return raw.encode("utf-8")
    except Exception:
        return None


def encrypt(text: str, key: bytes | None = None) -> str:
    """
    Chiffre un texte avec Fernet (AES-128-CBC + HMAC-SHA256).

    Args:
        text: Texte en clair à chiffrer (email, téléphone...).
        key:  Clé Fernet en bytes. Si None, utilise FERNET_KEY du .env.

    Returns:
        str: Token chiffré (ex: "gAAAAABk7x...").
             Retourne le texte original si la clé est absente (dégradation).

    Raises:
        ValueError: Si la clé est invalide.
    """
    if not text or not text.strip():
        return text

    fernet_key = key or _load_key()
    if not fernet_key:
        return text  # Pas de clé → pas de chiffrement (dégradation gracieuse)

    f = Fernet(fernet_key)
    return f.encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt(token: str, key: bytes | None = None) -> str:
    """
    Déchiffre un token Fernet.

    Args:
        token: Token chiffré (commence par "gAAAAAB...").
        key:   Clé Fernet en bytes. Si None, utilise FERNET_KEY du .env.

    Returns:
        str: Texte en clair si le déchiffrement réussit.
             "[DONNÉE PROTÉGÉE]" si la clé est absente ou invalide.
             La valeur originale si le token n'est pas chiffré (idempotence).
    """
    if not token or not token.strip():
        return token

    # Si le token ne ressemble pas à un token Fernet, le retourner tel quel
    # (permet l'idempotence : un champ déjà en clair ne plante pas)
    if not token.startswith("gAAAAAB"):
        return token

    fernet_key = key or _load_key()
    if not fernet_key:
        return "[DONNÉE PROTÉGÉE]"

    try:
        f = Fernet(fernet_key)
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return "[DONNÉE PROTÉGÉE]"
    except Exception:
        return "[DONNÉE PROTÉGÉE]"


def is_encrypted(value: str) -> bool:
    """
    Vérifie si une valeur est déjà chiffrée par Fernet.
    Utilisé pour éviter le re-chiffrement (idempotence).

    Args:
        value: Valeur à tester.

    Returns:
        bool: True si la valeur commence par le préfixe Fernet "gAAAAAB".
    """
    return isinstance(value, str) and value.startswith("gAAAAAB")


# --------------------------------------------------------------------------- #
#  Test autonome                                                               #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    print("=" * 60)
    print("  SmartRecruit AI — Encryption Test | Sprint D")
    print("=" * 60)

    key = _load_key()
    if not key:
        print("\n  [ERREUR] FERNET_KEY absente du .env")
        print("  Générez-en une avec :")
        print("  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
        exit(1)

    print(f"\n  Clé chargée : {key[:20].decode()}...")

    TEST_VALUES = [
        ("alice.dupont@gmail.com",  "Email"),
        ("+33 6 12 34 56 78",       "Téléphone"),
        ("",                         "Vide"),
    ]

    all_pass = True
    for original, label in TEST_VALUES:
        if not original:
            continue
        chiffre    = encrypt(original, key)
        dechiffre  = decrypt(chiffre, key)
        idempotent = not is_encrypted(decrypt(original, key))  # déchiffrer du clair → inchangé

        ok = (dechiffre == original)
        status = "✅ PASS" if ok else "❌ FAIL"
        if not ok:
            all_pass = False

        print(f"\n  {status} [{label}]")
        print(f"  Original  : {original}")
        print(f"  Chiffré   : {chiffre[:35]}...")
        print(f"  Déchiffré : {dechiffre}")

    # Test clé manquante
    donne_protegee = decrypt("gAAAAABkFAKETOKEN_invalid", b"")
    print(f"\n  ✅ Clé manquante → '{donne_protegee}'") if donne_protegee == "[DONNÉE PROTÉGÉE]" else print("❌ FAIL")

    print(f"\n{'=' * 60}")
    print(f"  Résultat : {'✅ Tous les tests passés' if all_pass else '❌ Échecs détectés'}")
    print(f"{'=' * 60}\n")
