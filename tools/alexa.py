"""Alexa (Amazon Echo) — via alexapy (lib communautaire, non officielle).

⚠️ Honnêteté : Amazon n'a AUCUNE API officielle pour piloter tes appareils Alexa
depuis un tiers. La voie viable (celle de Home Assistant) est `alexapy` : connexion
au compte Amazon par cookie (login + 2FA), puis :
  - faire parler un Echo (TTS / annonce),
  - contrôler le média (play/pause/volume),
  - **déclencher une Routine** Alexa par son énoncé -> contrôle INDIRECT des appareils
    (crée une routine « lumière salon on » dans l'app Alexa, Jarvis la déclenche),
  - lister les Echo + leur état.

Fragile par nature (Amazon change/casse l'accès non officiel). L'auth se fait UNE fois
en interactif : `python scripts/alexa_login.py` (gère captcha/2FA), le cookie est
réutilisé ensuite. Credentials dans config.yaml (jamais en dur). Voir docs/alexa.md.

Niveaux : etat/media/annoncer = N1 ; routine = N2 (une routine peut être impactante).
"""
import asyncio
import logging
import threading
from pathlib import Path

from core.config import reglage
from core.registre import outil
from core.util import sans_accents

LOG = logging.getLogger("jarvis")
_RACINE = Path(__file__).resolve().parent.parent
_LOOP = None
_LOGIN = None            # AlexaLogin connecté (réutilisé)
_VERROU = threading.Lock()


# ------------------------------------------------------ pont async -> sync

def _boucle():
    global _LOOP
    if _LOOP is None:
        _LOOP = asyncio.new_event_loop()
        threading.Thread(target=_LOOP.run_forever, daemon=True, name="alexa-loop").start()
    return _LOOP


def _run(coro, timeout=40):
    return asyncio.run_coroutine_threadsafe(coro, _boucle()).result(timeout=timeout)


# ------------------------------------------------------ config / login

def _configure():
    return bool(reglage("alexa.email", "") and reglage("alexa.password", ""))


def _msg_config():
    return ("Alexa n'est pas configuré. Renseigne alexa.email / alexa.password "
            "(et alexa.otp_secret pour le 2FA) dans config.yaml, puis lance "
            "« python scripts/alexa_login.py » — voir docs/alexa.md.")


def _cookie_path(fichier):
    d = _RACINE / (reglage("alexa.dossier", "logs/alexa"))
    d.mkdir(parents=True, exist_ok=True)
    return str(d / fichier)


async def _assurer_login():
    """Renvoie un AlexaLogin connecté (via le cookie sauvegardé). Lève sinon."""
    global _LOGIN
    if _LOGIN is not None:
        try:
            if await _LOGIN.test_loggedin():
                return _LOGIN
        except Exception:
            _LOGIN = None
    from alexapy import AlexaLogin
    login = AlexaLogin(
        url=reglage("alexa.url", "amazon.fr"),
        email=reglage("alexa.email", ""), password=reglage("alexa.password", ""),
        outputpath=_cookie_path, otp_secret=(reglage("alexa.otp_secret", "") or ""),
        oauth_login=False)
    cookies = login.load_cookie()
    if cookies and await login.test_loggedin(cookies):
        _LOGIN = login
        return login
    # Pas de session valide : la connexion interactive est requise (captcha/2FA).
    raise RuntimeError("Connexion Alexa requise : lance « python scripts/alexa_login.py ».")


async def _devices(login):
    from alexapy import AlexaAPI
    return await AlexaAPI.get_devices(login) or []


def _choisir(devices, cible):
    en_ligne = [d for d in devices if d.get("online")]
    if cible:
        c = sans_accents(cible.lower())
        for d in devices:
            if c in sans_accents(str(d.get("accountName", "")).lower()):
                return d
    return en_ligne[0] if en_ligne else (devices[0] if devices else None)


# ------------------------------------------------------ coroutines d'action

async def _etat():
    login = await _assurer_login()
    devices = await _devices(login)
    if not devices:
        return "Aucun appareil Alexa trouvé sur le compte."
    lignes = [f"{d.get('accountName','?')} ({'en ligne' if d.get('online') else 'hors ligne'})"
              for d in devices]
    return "Appareils Alexa : " + " ; ".join(lignes) + "."


async def _annoncer(texte, cible):
    from alexapy import AlexaAPI
    login = await _assurer_login()
    devices = await _devices(login)
    dev = _choisir(devices, cible)
    if dev is None:
        return "Aucun Echo disponible pour parler."
    api = AlexaAPI(dev, login)
    if cible:
        await api.send_tts(texte)
        return f"C'est dit sur {dev.get('accountName','')}."
    await api.send_announcement(texte)
    return "Annonce diffusée sur tes Echo."


async def _routine(nom):
    from alexapy import AlexaAPI
    login = await _assurer_login()
    devices = await _devices(login)
    dev = _choisir(devices, "")
    if dev is None:
        return "Aucun Echo pour déclencher la routine."
    await AlexaAPI(dev, login).run_routine(nom)
    return f"Routine « {nom} » déclenchée."


async def _media(action, cible, niveau):
    from alexapy import AlexaAPI
    login = await _assurer_login()
    dev = _choisir(await _devices(login), cible)
    if dev is None:
        return "Aucun Echo disponible."
    api = AlexaAPI(dev, login)
    a = (action or "").lower().strip()
    if a in ("pause", "stop"):
        await api.pause()
        return "En pause."
    if a in ("play", "lecture", "reprend"):
        await api.play()
        return "Lecture."
    if a in ("volume",):
        await api.set_volume(max(0.0, min(1.0, (niveau or 50) / 100.0)))
        return f"Volume à {niveau}%."
    return f"Action média inconnue : {action} (play, pause, volume)."


# ------------------------------------------------------ outils

def _err(e):
    return f"Alexa a échoué ({str(e)[:140]})."


@outil(
    nom="alexa_etat",
    description="Liste tes appareils Alexa (Echo) et leur état. Pour 'mes appareils "
                "Alexa', 'quels Echo sont en ligne'.",
    lent=True, phrase_attente="Je regarde tes appareils Alexa.",
)
def alexa_etat() -> str:
    if not _configure():
        return _msg_config()
    try:
        return _run(_etat())
    except Exception as e:
        return _err(e)


@outil(
    nom="alexa_annoncer",
    description="Fait parler un Echo (annonce / TTS). Pour 'annonce sur Alexa ...', "
                "'fais dire à Alexa ...', 'préviens la maison que ...'.",
    parametres={
        "type": "object",
        "properties": {
            "texte": {"type": "string", "description": "Le message à annoncer."},
            "cible": {"type": "string", "description": "Nom d'un Echo précis (optionnel ; "
                                                       "vide = annonce sur tous)."},
        },
        "required": ["texte"],
    },
)
def alexa_annoncer(texte: str, cible: str = "") -> str:
    if not _configure():
        return _msg_config()
    try:
        return _run(_annoncer(texte, cible))
    except Exception as e:
        return _err(e)


@outil(
    nom="alexa_routine",
    description="Déclenche une Routine Alexa par son énoncé (le contrôle des appareils "
                "Google/Alexa passe par des routines que tu crées dans l'app Alexa, ex. "
                "'lumière salon on'). Pour 'lance la routine ...', 'active ...'.",
    parametres={
        "type": "object",
        "properties": {
            "nom": {"type": "string", "description": "L'énoncé de la routine (comme dans "
                                                     "l'app Alexa, ex. 'bonne nuit')."}
        },
        "required": ["nom"],
    },
    confirmation=True,
    annonce=lambda a: f"Je vais déclencher la routine Alexa « {a.get('nom','')} ».",
)
def alexa_routine(nom: str) -> str:
    if not _configure():
        return _msg_config()
    try:
        return _run(_routine(nom))
    except Exception as e:
        return _err(e)


@outil(
    nom="alexa_media",
    description="Contrôle la lecture sur un Echo : play, pause, ou volume. Pour 'mets "
                "en pause sur Alexa', 'reprends la musique sur l'Echo', 'volume Alexa à 30'.",
    parametres={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["play", "pause", "volume"]},
            "cible": {"type": "string", "description": "Nom d'un Echo précis (optionnel)."},
            "niveau": {"type": "integer", "description": "Volume 0-100 (si action=volume)."},
        },
        "required": ["action"],
    },
)
def alexa_media(action: str, cible: str = "", niveau: int = 50) -> str:
    if not _configure():
        return _msg_config()
    try:
        return _run(_media(action, cible, niveau))
    except Exception as e:
        return _err(e)
