"""Connexion interactive à Alexa (à faire UNE fois) — gère captcha / 2FA.

    python scripts/alexa_login.py

Se connecte au compte Amazon (email/password de config.yaml), gère le captcha et le
2FA en interactif, et sauvegarde le cookie de session (dans logs/alexa/). Les outils
Alexa réutilisent ensuite ce cookie sans nouvelle connexion. Voir docs/alexa.md.

⚠️ alexapy est une lib communautaire non officielle : l'auth peut casser si Amazon
change quelque chose. Si les outils Alexa disent « connexion requise », relance ce script.
"""
import asyncio
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from core.config import reglage  # noqa: E402


def _cookie_path(fichier):
    d = RACINE / (reglage("alexa.dossier", "logs/alexa"))
    d.mkdir(parents=True, exist_ok=True)
    return str(d / fichier)


async def main():
    if not (reglage("alexa.email", "") and reglage("alexa.password", "")):
        print("Renseigne d'abord alexa.email / alexa.password dans config.yaml.")
        return
    from alexapy import AlexaLogin
    login = AlexaLogin(
        url=reglage("alexa.url", "amazon.fr"),
        email=reglage("alexa.email", ""), password=reglage("alexa.password", ""),
        outputpath=_cookie_path, otp_secret=(reglage("alexa.otp_secret", "") or ""))

    data = None
    for _ in range(8):
        await login.login(data=data)
        st = login.status or {}
        if st.get("login_successful"):
            print("\n✅ Connecté à Alexa. Cookie sauvegardé dans logs/alexa/.")
            print("   Les outils Alexa sont prêts (« Jarvis, mes appareils Alexa »).")
            return
        if st.get("login_failed"):
            print("\n❌ Échec de connexion :", st.get("login_failed"))
            return
        data = {}
        if st.get("captcha_required"):
            print("\nCaptcha à résoudre :", st.get("captcha_image_url", "(voir navigateur)"))
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
            print("\nÉtat inattendu (rien à saisir) :", st)
            return
    print("\nTrop de tentatives — recommence.")


if __name__ == "__main__":
    asyncio.run(main())
