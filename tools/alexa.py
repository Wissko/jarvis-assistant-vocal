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
import json
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
    p = d / fichier
    p.parent.mkdir(parents=True, exist_ok=True)   # crée « .storage/ » si besoin
    return str(p)


# Tokens OAuth durables (refresh_token/mac_dms), sauvés par scripts/alexa_login.py.
# C'est la voie réutilisable : le cookie seul ne réauthentifie pas l'API Alexa.
_OAUTH_CLES = ("access_token", "refresh_token", "mac_dms", "expires_in")


def _oauth_path():
    d = _RACINE / (reglage("alexa.dossier", "logs/alexa")) / ".storage"
    return d / f"alexa_media.{reglage('alexa.email', '')}.oauth.json"


def _charger_oauth():
    p = _oauth_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


def _sauver_oauth(login):
    try:
        p = _oauth_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({k: getattr(login, k, None) for k in _OAUTH_CLES}),
                     encoding="utf-8")
    except Exception:
        pass


async def _assurer_login():
    """Renvoie un AlexaLogin connecté (via les tokens OAuth sauvés). Lève sinon."""
    global _LOGIN
    if _LOGIN is not None:
        try:
            if await _LOGIN.test_loggedin():
                return _LOGIN
        except Exception:
            _LOGIN = None
    from alexapy import AlexaLogin
    oauth = _charger_oauth()
    login = AlexaLogin(
        url=reglage("alexa.url", "amazon.fr"),
        email=reglage("alexa.email", ""), password=reglage("alexa.password", ""),
        outputpath=_cookie_path, otp_secret=(reglage("alexa.otp_secret", "") or ""),
        oauth=oauth)
    # login() : voie refresh_token en priorité (rebuild silencieux), cookie en repli.
    cookies = await login.load_cookie()
    await login.login(cookies=cookies)
    if await login.test_loggedin():
        _sauver_oauth(login)   # persiste le token éventuellement rafraîchi
        _LOGIN = login
        return login
    raise RuntimeError("Connexion Alexa requise : lance « python scripts/alexa_login.py ».")


async def _devices(login):
    from alexapy import AlexaAPI
    return await AlexaAPI.get_devices(login) or []


class _Appareil:
    """Enveloppe le dict de get_devices en OBJET attendu par AlexaAPI.

    alexapy accède à ._device_type / .device_serial_number / ._locale / etc. sur
    l'appareil (Home Assistant lui passe sa propre classe). get_devices() ne renvoie
    que des dicts → sans cette enveloppe : « 'dict' object has no attribute _locale ».
    """

    def __init__(self, d):
        self._device_type = d.get("deviceType")
        self.device_serial_number = d.get("serialNumber")
        self._device_family = d.get("deviceFamily")
        self._cluster_members = d.get("clusterMembers") or []
        self._locale = d.get("locale")   # absent chez Amazon → None → défaut alexapy


def _api(dev, login):
    from alexapy import AlexaAPI
    return AlexaAPI(_Appareil(dev), login)


# Familles qui ne « parlent » pas (annonce/TTS) : Fire TV, l'app, tablettes, groupe.
_FAMILLES_NON_PARLANTES = {"FIRE_TV", "VOX", "TABLET", "MOBILE_DEVICE", "WHA"}


def _est_haut_parleur(d):
    return str(d.get("deviceFamily", "")).upper() not in _FAMILLES_NON_PARLANTES


def _choisir(devices, cible, parlant=False):
    en_ligne = [d for d in devices if d.get("online")]
    if cible:
        c = sans_accents(cible.lower())
        for d in devices:
            if c in sans_accents(str(d.get("accountName", "")).lower()):
                return d
    if parlant:   # annonce/TTS sans cible → privilégier un vrai Echo (ex. Echo Show)
        parleurs = [d for d in en_ligne if _est_haut_parleur(d)]
        if parleurs:
            return parleurs[0]
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
    login = await _assurer_login()
    devices = await _devices(login)
    dev = _choisir(devices, cible, parlant=True)
    if dev is None:
        return "Aucun Echo disponible pour parler."
    api = _api(dev, login)
    if cible:
        await api.send_tts(texte)
        return f"C'est dit sur {dev.get('accountName','')}."
    await api.send_announcement(texte)
    return "Annonce diffusée sur tes Echo."


def _liste_noms(autos):
    return [n for n in (_nom_routine(a) for a in autos if isinstance(a, dict)) if n]


def _trouver_exact(autos, nom):
    """Routine dont le nom OU un énoncé == nom (insensible casse/accents)."""
    cible = sans_accents(nom).lower().strip()
    for a in autos:
        if not isinstance(a, dict):
            continue
        if any(sans_accents(p).lower().strip() == cible for p in _phrases_routine(a)):
            return _nom_routine(a)
    return None


async def _routine(nom):
    login = await _assurer_login()
    autos = await _automations(login)
    # run_routine() échoue EN SILENCE si rien ne matche → on vérifie d'abord,
    # sinon on annoncerait un faux succès (« déclenchée » alors que rien ne bouge).
    trouve = _trouver_exact(autos, nom)
    if trouve is None:
        noms = _liste_noms(autos)
        noms_txt = ", ".join(noms[:8]) or "aucune (à créer dans l'app Alexa)"
        return f"Aucune routine « {nom} » chez toi. Tes routines : {noms_txt}."
    dev = _choisir(await _devices(login), "")
    await _api(dev, login).run_routine(trouve)
    return f"Routine « {trouve} » déclenchée."


# ---- contrôle naturel : « allume la clim » -> routine Alexa correspondante ----

_MOTS_ON = {"on", "allume", "allumer", "active", "activer", "marche", "ouvre",
            "ouvrir", "demarre", "demarrer", "lance", "monte"}
_MOTS_OFF = {"off", "eteins", "eteindre", "eteint", "coupe", "couper", "arrete",
             "arreter", "desactive", "desactiver", "ferme", "fermer", "stop", "baisse"}


async def _automations(login):
    from alexapy import AlexaAPI
    return await AlexaAPI.get_automations(login) or []


def _phrases_routine(a):
    """Tous les libellés d'une routine : son nom + ses énoncés vocaux."""
    ph = []
    nom = a.get("name")
    if isinstance(nom, str) and nom.strip():
        ph.append(nom)
    trigs = a.get("triggers")
    if isinstance(trigs, list) and trigs and isinstance(trigs[0], dict):
        pay = trigs[0].get("payload")
        if isinstance(pay, dict):
            if isinstance(pay.get("utterance"), str):
                ph.append(pay["utterance"])
            for x in (pay.get("utterances") or []):
                if isinstance(x, str):
                    ph.append(x)
    return ph


def _nom_routine(a):
    for p in _phrases_routine(a):
        return p            # le nom en priorité, sinon le 1er énoncé
    return None


def _mot_present(mot, blob, blob_mots):
    """Présence tolérante (sous-chaîne, ou même préfixe 4+ : lumiere ~ lumieres)."""
    if mot in blob:
        return True
    return any(len(w) >= 4 and (w.startswith(mot[:4]) or mot.startswith(w[:4]))
               for w in blob_mots)


# Synonymes courants d'appareils (sans accents) : « télé » doit matcher « tv », etc.
_SYNONYMES = [
    {"tv", "tele", "television", "televiseur"},
    {"clim", "climatisation", "climatiseur", "clime"},
    {"lumiere", "lumieres", "lampe", "lampes", "eclairage", "lumieres"},
    {"ventilateur", "ventilo"},
    {"volet", "volets", "store", "stores"},
    {"prise", "prises"},
]


def _variantes(mot):
    for grp in _SYNONYMES:
        if mot in grp:
            return grp
    return {mot}


def _appareil_present(mot, blob, blob_mots):
    return any(_mot_present(v, blob, blob_mots) for v in _variantes(mot))


def _resoudre_routine(automations, appareil, on):
    """Trouve la routine correspondant à (appareil, on/off). Renvoie (nom, message)."""
    app_mots = [m for m in sans_accents(appareil).lower().split() if len(m) >= 2]
    cible = _MOTS_ON if on else _MOTS_OFF
    exact, appareil_seul = [], []
    for a in automations:
        if not isinstance(a, dict):
            continue
        nom = _nom_routine(a)
        if not nom:
            continue
        blob = sans_accents(" ".join(_phrases_routine(a))).lower()
        blob_mots = blob.replace("-", " ").split()
        if app_mots and not all(_appareil_present(m, blob, blob_mots) for m in app_mots):
            continue                                   # pas le bon appareil
        (exact if set(blob_mots) & cible else appareil_seul).append(nom)
    if exact:
        return exact[0], None
    if len(appareil_seul) == 1:                         # une seule routine (bascule)
        return appareil_seul[0], None
    if appareil_seul:
        return None, ("Plusieurs routines correspondent : "
                      + ", ".join(f"« {n} »" for n in appareil_seul[:6])
                      + ". Précise, ou dis « lance la routine <nom> ».")
    return None, ""


async def _appareil(appareil, action):
    login = await _assurer_login()
    autos = await _automations(login)
    if not autos:
        return ("Aucune routine Alexa n'existe. Crée-en une dans l'app Alexa "
                "(ex. « clim on » / « clim off ») — voir docs/alexa.md.")
    on = not (set(sans_accents(action or "").lower().split()) & _MOTS_OFF)
    nom, msg = _resoudre_routine(autos, appareil, on)
    if nom is None:
        if msg:
            return msg
        noms = [n for n in (_nom_routine(a) for a in autos if isinstance(a, dict)) if n]
        premier = (sans_accents(appareil).lower().split() or ["appareil"])[0]
        return (f"Pas de routine pour « {appareil} ». Tes routines : "
                f"{', '.join(noms[:8]) or 'aucune'}. Crée « {premier} on » et "
                f"« {premier} off » dans l'app Alexa.")
    dev = _choisir(await _devices(login), "")
    await _api(dev, login).run_routine(nom)
    return f"C'est fait — routine « {nom} » déclenchée."


async def _media(action, cible, niveau):
    login = await _assurer_login()
    dev = _choisir(await _devices(login), cible)
    if dev is None:
        return "Aucun Echo disponible."
    api = _api(dev, login)
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
    nom="alexa_appareil",
    description="Allume ou éteint un appareil connecté de la maison (clim, télé, "
                "lumières, prise, ventilateur…) en déclenchant la routine Alexa qui "
                "porte ce nom. Pour « allume la clim », « éteins la télé », « allume "
                "les lumières du salon », « coupe le ventilateur ». Retrouve la bonne "
                "routine parmi les tiennes (tolérant aux accents/pluriels).",
    parametres={
        "type": "object",
        "properties": {
            "appareil": {"type": "string", "description": "L'appareil ou la pièce, "
                         "ex. 'clim', 'télé', 'lumières salon', 'ventilateur'."},
            "action": {"type": "string", "enum": ["allumer", "eteindre"],
                       "description": "allumer (on) ou eteindre (off)."},
        },
        "required": ["appareil", "action"],
    },
)
def alexa_appareil(appareil: str, action: str = "allumer") -> str:
    if not _configure():
        return _msg_config()
    try:
        return _run(_appareil(appareil, action))
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
