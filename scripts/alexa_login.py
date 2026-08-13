"""Connexion Alexa assistée par navigateur (à faire UNE fois).

    python scripts/alexa_login.py

Amazon a fermé le login « headless » par identifiants. La méthode qui marche
(celle de Home Assistant) : un **proxy local** ouvre une page où tu te connectes
**normalement dans ton navigateur** (email, mot de passe, captcha, 2FA — tout se
fait chez Amazon), et le proxy **capture la session**. Le cookie est sauvegardé
dans logs/alexa/, réutilisé ensuite par les outils Alexa. Voir docs/alexa.md.

⚠️ alexapy est une lib communautaire non officielle : ça peut casser si Amazon
change quelque chose. Détail des échecs : logs/alexa/login-debug.log.
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
    # alexapy écrit dans un sous-dossier « .storage/… » : créer le parent, sinon
    # la sauvegarde du cookie échoue en silence (OSError catchée par alexapy).
    p = _dossier() / fichier
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def _activer_debug():
    h = logging.FileHandler(_dossier() / "login-debug.log", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    for nom in ("alexapy", "authcaptureproxy"):
        lg = logging.getLogger(nom)
        lg.setLevel(logging.DEBUG)
        lg.addHandler(h)


async def main():
    if not (reglage("alexa.email", "") and reglage("alexa.password", "")):
        print("Renseigne d'abord alexa.email / alexa.password dans config.yaml.")
        return
    _activer_debug()
    from alexapy import AlexaLogin, AlexaProxy

    port = int(reglage("alexa.proxy_port", 3000))
    login = AlexaLogin(
        url=reglage("alexa.url", "amazon.fr"),
        email=reglage("alexa.email", ""), password=reglage("alexa.password", ""),
        outputpath=_cookie_path, otp_secret=(reglage("alexa.otp_secret", "") or ""))
    proxy = AlexaProxy(login, f"http://127.0.0.1:{port}")

    await proxy.start_proxy()
    url_ouvrir = str(proxy.access_url())
    print("\n" + "=" * 64)
    print("  Ouvre CETTE adresse dans ton navigateur (sur ce PC) :")
    print("     ", url_ouvrir)
    print("  Connecte-toi à Amazon normalement (email, mot de passe, 2FA).")
    print("  Ton email/mot de passe sont pré-remplis ; fais juste le captcha/2FA.")
    print("=" * 64 + "\n  En attente de la connexion... (Ctrl+C pour annuler)")

    connecte = False
    try:
        for i in range(600):  # ~10 min
            if (login.status or {}).get("login_successful"):
                connecte = True
                break
            # Toutes les ~4 s : validation RÉELLE de la session (vraie requête Alexa).
            if i and i % 4 == 0:
                try:
                    # rebuild_session=False : ne pas recréer la session (garde les
                    # cookies injectés par le proxy).
                    if await login.test_loggedin(rebuild_session=False):
                        connecte = True
                        break
                except Exception:
                    pass
            await asyncio.sleep(1)

        if not connecte:
            print("\n⏱ Délai dépassé sans détecter la connexion.")
            print("   Si le navigateur te dit pourtant que tu es connecté, relance ce")
            print("   script, ou envoie-moi la fin de logs/alexa/login-debug.log.")
            return

        # Persiste explicitement : finalize_login() pose le drapeau ET sauve le cookie.
        # (Le proxy ne l'appelle pas toujours de lui-même.)
        if not (login.status or {}).get("login_successful"):
            await login.finalize_login()

        saved = await login.load_cookie()
        if saved:
            print("\n✅ Connecté à Alexa ! Cookie sauvegardé (", len(saved), "éléments) dans",
                  _dossier())
            print("   Redémarre Jarvis, puis dis « mes appareils Alexa ».")
        else:
            print("\n⚠️ Connecté, mais le cookie n'a pas pu être sauvegardé.")
            print("   Envoie-moi la fin de logs/alexa/login-debug.log.")
    except KeyboardInterrupt:
        print("\nAnnulé.")
    finally:
        try:
            await proxy.stop_proxy()
        except Exception:
            pass
        try:
            await login.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
