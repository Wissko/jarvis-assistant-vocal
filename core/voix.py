"""Pont vers la synthese vocale.

Permet aux outils (ex. le minuteur) de parler sans dependre de jarvis14.py,
ce qui evite les imports circulaires. jarvis14 enregistre sa fonction `dire`
via definir_parleur() au demarrage.
"""
import re

_parleur = None


def definir_parleur(fonction):
    global _parleur
    _parleur = fonction


def parler(texte):
    if _parleur is not None:
        _parleur(texte)


def texte_a_prononcer(texte, nom="", prononciation=""):
    """Change uniquement la forme parlee d'un nom, sans modifier l'ecrit du HUD."""
    if not nom or not prononciation:
        return str(texte or "")
    motif = rf"(?<!\w){re.escape(str(nom))}(?!\w)"
    return re.sub(motif, str(prononciation), str(texte or ""), flags=re.IGNORECASE)
