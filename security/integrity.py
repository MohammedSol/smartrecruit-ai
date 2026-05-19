"""
security/integrity.py
======================
Sprint C — Intégrité HMAC (Protection contre le Knowledge Base Poisoning).

Principe :
    Lors de l'indexation d'un document dans ChromaDB, on calcule son empreinte
    HMAC-SHA256 et on la stocke dans les métadonnées. Lors du retrieval, on
    recalcule l'empreinte et on compare. Si le texte a été modifié (même d'un
    seul caractère), la vérification échoue et le document est rejeté.

    hmac.compare_digest() est utilisé à la place de == pour éviter les attaques
    par timing side-channel (l'attaquant ne peut pas déduire combien de
    caractères sont corrects en mesurant le temps de réponse).

Dégradation gracieuse :
    Si ce fichier est supprimé, le bloc try/except dans retriever.py
    considère tous les documents comme valides (is_valid=True par défaut).
    L'application continue sans vérification d'intégrité.

Usage :
    from security.integrity import sign, verify

    # À l'indexation :
    sig = sign(text, "demo-secret")
    metadatas = {"community_id": "comm_1", "hmac_signature": sig}

    # Au retrieval :
    is_valid = verify(text, sig, "demo-secret")
"""

import hmac
import hashlib


def sign(text: str, secret_key: str) -> str:
    """
    Calcule la signature HMAC-SHA256 d'un texte.

    Args:
        text:       Texte à signer (résumé de communauté).
        secret_key: Clé secrète partagée entre l'indexeur et le retriever.

    Returns:
        str: Signature hexadécimale (64 caractères).

    Example:
        >>> sign("Candidat expert Python", "demo-secret")
        'a3f8c2...'  # 64 chars hex
    """
    return hmac.new(
        key=secret_key.encode("utf-8"),
        msg=text.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def verify(text: str, signature: str, secret_key: str) -> bool:
    """
    Vérifie qu'un texte correspond à une signature HMAC-SHA256 donnée.

    Utilise hmac.compare_digest() pour une comparaison à temps constant
    (protection contre les attaques par timing side-channel).

    Args:
        text:       Texte reçu (potentiellement modifié).
        signature:  Signature stockée lors de l'indexation.
        secret_key: Même clé secrète que lors de la signature.

    Returns:
        bool: True si le texte est intact, False si corrompu/modifié.

    Example:
        >>> sig = sign("Texte original", "demo-secret")
        >>> verify("Texte original", sig, "demo-secret")
        True
        >>> verify("Texte modifié!", sig, "demo-secret")
        False
    """
    if not signature:
        # Pas de signature stockée = document antérieur au Sprint C
        # On le considère valide pour ne pas bloquer les anciens documents
        return True

    expected = sign(text, secret_key)
    return hmac.compare_digest(expected, signature)


# --------------------------------------------------------------------------- #
#  Test autonome (python security/integrity.py)                               #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    SECRET = "demo-secret"

    TEST_CASES = [
        ("Candidat expert Python",           "Candidat expert Python",           True),
        ("Candidat expert Python",           "Candidat expert Python X",         False),
        ("Ingénieur DevOps Kubernetes",      "Ingénieur DevOps Kubernetes",      True),
        ("Ingénieur DevOps Kubernetes",      "Ingénieur DevOps Kubernetes!hack", False),
        ("",                                 "",                                 True),
    ]

    print("=" * 60)
    print("  SmartRecruit AI — HMAC Integrity | Test Sprint C")
    print("=" * 60)

    passed = 0
    for original, tampered, expected_valid in TEST_CASES:
        sig = sign(original, SECRET)
        result = verify(tampered, sig, SECRET)
        ok = result == expected_valid
        status = "✅ PASS" if ok else "❌ FAIL"
        if ok:
            passed += 1

        label = "INTACT " if result else "CORROMPU"
        print(f"\n  {status} [{label}]")
        print(f"  Original : {original[:50] or '(vide)'!r}")
        if original != tampered:
            print(f"  Modifié  : {tampered[:50]!r}")

    print(f"\n{'=' * 60}")
    print(f"  Résultats : {passed}/{len(TEST_CASES)} tests passés")
    print(f"{'=' * 60}\n")
