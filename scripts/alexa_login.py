"""Connexion Alexa assistée par navigateur (à faire UNE fois).

    python scripts/alexa_login.py            # login par navigateur + vérif
    python scripts/alexa_login.py --check     # teste le cookie déjà sauvé (sans re-login)

Amazon a fermé le login « headless » par identifiants. La méthode qui marche
(celle de Home Assistant) : un **proxy local** ouvre une page où tu te connectes
**normalement dans ton navigateur** (email, mot de passe, captcha, 2FA — tout se
fait chez Amazon), et le proxy **capture la session**. Le cookie est sauvegardé
dans logs/alexa/.storage/, réutilisé ensuite par les outils Alexa.

⚠️ Point délicat : le proxy n'injecte les cookies dans la session qu'au moment où
ton navigateur atteint la **page finale Amazon** (« Successfully logged in »). Ce
script attend donc que la **session soit réellement peuplée** avant de sauver —
sinon on écrivait un cookie vide (d'où les « Connexion Alexa requise » passés).

alexapy est une lib communautaire non officielle : ça peut casser si Amazon change
quelque chose. Détail des échecs : logs/alexa/login-debug.log. Voir docs/alexa.md.
"""
import asyncio
import logging
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from core.config import reglage  # noqa: E402

# Console Windows en cp1252 : les emoji/cadres feraient planter les print(). On
# force UTF-8 en sortie (errors=replace) pour ne jamais casser un diagnostic.
for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


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


def _chemin_cookie_reel(email):
    """Le fichier .cookies principal, tel que le nomme alexapy (_cookiefile[0])."""
    return Path(_cookie_path(f".storage/alexa_media.{email}.cookies"))


def _activer_debug():
    h = logging.FileHandler(_dossier() / "login-debug.log", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    for nom in ("alexapy", "authcaptureproxy"):
        lg = logging.getLogger(nom)
        lg.setLevel(logging.DEBUG)
        lg.addHandler(h)


def _nouveau_login():
    from alexapy import AlexaLogin
    return AlexaLogin(
        url=reglage("alexa.url", "amazon.fr"),
        email=reglage("alexa.email", ""), password=reglage("alexa.password", ""),
        outputpath=_cookie_path, otp_secret=(reglage("alexa.otp_secret", "") or ""))


def _nb_cookies_session(login):
    try:
        return sum(1 for _ in login.session.cookie_jar)
    except Exception:
        return 0


async def _verifier_fichier(login, email):
    """Diagnostic dur : le cookie est-il sur disque, non vide, et rechargeable ?"""
    chemin = _chemin_cookie_reel(email)
    existe = chemin.exists()
    taille = chemin.stat().st_size if existe else 0
    recharge = await login.load_cookie()
    n = len(recharge or {})
    print("\n── Vérification du cookie ───────────────────────────────")
    print(f"  Fichier : {chemin}")
    print(f"  Existe  : {'oui' if existe else 'NON'}   Taille : {taille} octets")
    print(f"  Cookies dans la session capturée : {_nb_cookies_session(login)}")
    print(f"  Cookies rechargés depuis le fichier : {n}")
    print("─────────────────────────────────────────────────────────")
    return existe and taille > 0 and n > 0


async def _check():
    """Teste le cookie déjà sauvegardé par un VRAI appel Alexa (sans re-login)."""
    email = reglage("alexa.email", "")
    if not email:
        print("Renseigne d'abord alexa.email / alexa.password dans config.yaml.")
        return
    _activer_debug()
    chemin = _chemin_cookie_reel(email)
    print(f"Cookie attendu : {chemin}")
    if not chemin.exists():
        print("❌ Aucun cookie sauvegardé. Lance « python scripts/alexa_login.py ».")
        return
    from alexapy import AlexaAPI
    login = _nouveau_login()
    try:
        cookies = await login.load_cookie()
        print(f"Cookies chargés : {len(cookies or {})}")
        await login.login(cookies=cookies)
        if not await login.test_loggedin():
            print("❌ Session refusée par Amazon (cookie expiré ?). Relance le login.")
            return
        devices = await AlexaAPI.get_devices(login) or []
        print(f"✅ Connecté. {len(devices)} appareil(s) Alexa :")
        for d in devices:
            print(f"   · {d.get('accountName','?')} "
                  f"({'en ligne' if d.get('online') else 'hors ligne'})")
    finally:
        try:
            await login.close()
        except Exception:
            pass


async def _login_navigateur():
    email = reglage("alexa.email", "")
    if not (email and reglage("alexa.password", "")):
        print("Renseigne d'abord alexa.email / alexa.password dans config.yaml.")
        return
    _activer_debug()
    from alexapy import AlexaProxy

    port = int(reglage("alexa.proxy_port", 3000))
    login = _nouveau_login()
    proxy = AlexaProxy(login, f"http://127.0.0.1:{port}")

    await proxy.start_proxy()
    url_ouvrir = str(proxy.access_url())
    print("\n" + "=" * 64)
    print("  Ouvre CETTE adresse dans ton navigateur (sur ce PC) :")
    print("     ", url_ouvrir)
    print("  Connecte-toi à Amazon normalement (email, mot de passe, 2FA).")
    print("  ⚠️ VA JUSQU'AU BOUT : attends la page « Successfully logged in »")
    print("     (sinon la session n'est pas capturée).")
    print("=" * 64 + "\n  En attente de la connexion... (Ctrl+C pour annuler)")

    connecte = False
    try:
        for i in range(600):  # ~10 min
            # Signal FIABLE : le handler du proxy (test_amazon_url) a peuplé la
            # session ET posé login_successful / access_token quand le navigateur
            # a atteint la page finale Amazon. On exige des cookies en session
            # pour ne JAMAIS sauver un cookie vide.
            statut_ok = bool((login.status or {}).get("login_successful")
                             or login.access_token)
            if statut_ok and _nb_cookies_session(login) > 0:
                connecte = True
                break
            # Filet : validation réelle de la session toutes les ~4 s.
            if i and i % 4 == 0 and _nb_cookies_session(login) > 0:
                try:
                    if await login.test_loggedin(rebuild_session=False):
                        connecte = True
                        break
                except Exception:
                    pass
            await asyncio.sleep(1)

        if not connecte:
            n = _nb_cookies_session(login)
            print("\n⏱ Délai dépassé sans capturer la session "
                  f"(cookies en session : {n}).")
            if n == 0:
                print("   → Ton navigateur n'a pas atteint la page finale Amazon.")
                print("     Reprends et va jusqu'à « Successfully logged in ».")
            print("   Détails : logs/alexa/login-debug.log")
            return

        # Persiste (pose le drapeau ET sauve le cookie depuis la session peuplée).
        await login.finalize_login()

        if await _verifier_fichier(login, email):
            print("\n✅ Connecté à Alexa, cookie vérifié sur disque.")
            print("   Redémarre Jarvis, puis dis « mes appareils Alexa »,")
            print("   ou teste tout de suite : python scripts/alexa_login.py --check")
        else:
            print("\n⚠️ Login OK mais le cookie n'est pas exploitable (voir ci-dessus).")
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


async def main():
    if "--check" in sys.argv:
        await _check()
    else:
        await _login_navigateur()


if __name__ == "__main__":
    asyncio.run(main())
