"""Connexion interactive à Alexa (à faire UNE fois) — gère captcha / 2FA.

    python scripts/alexa_login.py

Se connecte au compte Amazon (email/password de config.yaml) via le login classique
d'alexapy (oauth_login=False), gère le captcha et le 2FA en interactif, et sauvegarde
le cookie de session (dans logs/alexa/). Les outils Alexa réutilisent ensuite ce
cookie. Voir docs/alexa.md.

⚠️ alexapy est une lib communautaire non officielle : l'auth peut casser si Amazon
change quelque chose. En cas d'échec, le détail est écrit dans logs/alexa/login-debug.log.
"""
import asyncio
import logging
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from core.config import reglage  # noqa: E402


def _dossier():
    d = RACINE / (reglage("alexa.dossier", "logs/alexa"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cookie_path(fichier):
    return str(_dossier() / fichier)


def _activer_debug():
    """Logue le détail d'alexapy dans un fichier (les erreurs de login y sont tracées)."""
    h = logging.FileHandler(_dossier() / "login-debug.log", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    log = logging.getLogger("alexapy")
    log.setLevel(logging.DEBUG)
    log.addHandler(h)


async def main():
    if not (reglage("alexa.email", "") and reglage("alexa.password", "")):
        print("Renseigne d'abord alexa.email / alexa.password dans config.yaml.")
        return
    _activer_debug()
    from alexapy import AlexaLogin
    login = AlexaLogin(
        url=reglage("alexa.url", "amazon.fr"),
        email=reglage("alexa.email", ""), password=reglage("alexa.password", ""),
        outputpath=_cookie_path, otp_secret=(reglage("alexa.otp_secret", "") or ""),
        oauth_login=False)  # login email/mot de passe direct (pas OAuth device)

    try:
        data = None
        for _ in range(8):
            await login.login(data=data)
            if await login.test_loggedin():
                print("\n✅ Connecté à Alexa. Cookie sauvegardé dans",
                      _dossier(), "\n   Redémarre Jarvis puis dis « mes appareils Alexa ».")
                return
            st = login.status or {}
            data = {}
            if st.get("captcha_required"):
                print("\nCaptcha à résoudre — ouvre :", st.get("captcha_image_url", "(cf. debug)"))
                data["captcha"] = input("  Saisis le captcha : ").strip()
            if st.get("securitycode_required"):
                data["securitycode"] = input("  Code 2FA (SMS ou appli) : ").strip()
            if st.get("claimspicker_required"):
                print("\nMéthode de vérification :", st.get("claimspicker_message", ""))
                data["claimsoption"] = input("  Choix (numéro) : ").strip()
            if st.get("authselect_required"):
                print("\nSélection d'authentification :", st.get("authselect_message", ""))
                data["authselectoption"] = input("  Choix (numéro) : ").strip()
            if st.get("verificationcode_required"):
                data["verificationcode"] = input("  Code de vérification : ").strip()
            if not data:
                print("\n❌ Login échoué sans étape à saisir. Détail :",
                      "logs/alexa/login-debug.log")
                print("   Statut renvoyé :", st or "(vide)")
                print("   Pistes : mauvais mot de passe, mauvais domaine (alexa.url = "
                      "amazon.fr / .com / .de…), ou Amazon bloque le login sans navigateur "
                      "(connecte-toi d'abord sur le site Amazon depuis ce PC, puis relance).")
                return
        print("\nTrop de tentatives — recommence.")
    finally:
        try:
            await login.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
