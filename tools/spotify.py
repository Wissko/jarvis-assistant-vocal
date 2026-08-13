"""Spotify : ajoute la musique reconnue à une playlist « Jarvis Finds ».

« ajoute-la à ma playlist » (la dernière musique reconnue), et option d'ajout
AUTOMATIQUE à chaque reconnaissance (spotify.auto_ajout). Auth OAuth : login une
fois (scripts/spotify_login.py), refresh_token réutilisé ensuite.

N1/N2 (écriture dans TA playlist). Non exposé au MCP par défaut. Voir docs/spotify.md.
"""
import base64
import json
import threading
import time
from pathlib import Path

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass
import requests

from core.config import reglage
from core.registre import outil
from core.util import sans_accents

_RACINE = Path(__file__).resolve().parent.parent
_API = "https://api.spotify.com/v1"
_TOKEN = {"access": None, "exp": 0.0}
_PLAYLIST_ID = None
_VERROU = threading.Lock()


# ------------------------------------------------------ auth

def _fichier_token():
    return _RACINE / (reglage("spotify.dossier", "logs/spotify")) / "token.json"


def _refresh_token():
    f = _fichier_token()
    if f.exists():
        try:
            return (json.loads(f.read_text(encoding="utf-8")) or {}).get("refresh_token")
        except Exception:
            pass
    return reglage("spotify.refresh_token", "") or None


def _configure():
    return bool(reglage("spotify.client_id", "") and reglage("spotify.client_secret", "")
                and _refresh_token())


def _msg_config():
    return ("Spotify n'est pas connecté. Crée une app sur developer.spotify.com, mets "
            "client_id/secret dans config.yaml, puis lance "
            "« python scripts/spotify_login.py » — voir docs/spotify.md.")


def _access():
    if _TOKEN["access"] and time.time() < _TOKEN["exp"] - 30:
        return _TOKEN["access"]
    cid = reglage("spotify.client_id", "")
    secret = reglage("spotify.client_secret", "")
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    r = requests.post("https://accounts.spotify.com/api/token",
                      data={"grant_type": "refresh_token",
                            "refresh_token": _refresh_token()},
                      headers={"Authorization": f"Basic {auth}"}, timeout=15)
    r.raise_for_status()
    d = r.json()
    _TOKEN["access"] = d["access_token"]
    _TOKEN["exp"] = time.time() + int(d.get("expires_in", 3600))
    return _TOKEN["access"]


def _h():
    return {"Authorization": f"Bearer {_access()}",
            "Content-Type": "application/json"}


# ------------------------------------------------------ playlist / recherche

def _me():
    return requests.get(f"{_API}/me", headers=_h(), timeout=15).json()


def _playlist_id():
    """Id de la playlist cible (spotify.playlist ou « Jarvis Finds »), créée si besoin."""
    global _PLAYLIST_ID
    if _PLAYLIST_ID:
        return _PLAYLIST_ID
    nom = reglage("spotify.playlist", "Jarvis Finds")
    with _VERROU:
        # cherche parmi les playlists de l'utilisateur
        url = f"{_API}/me/playlists?limit=50"
        while url:
            d = requests.get(url, headers=_h(), timeout=15).json()
            for pl in d.get("items", []):
                if sans_accents((pl.get("name") or "").lower()) == sans_accents(nom.lower()):
                    _PLAYLIST_ID = pl["id"]
                    return _PLAYLIST_ID
            url = d.get("next")
        # sinon : la crée (privée)
        uid = _me()["id"]
        r = requests.post(f"{_API}/users/{uid}/playlists", headers=_h(),
                          data=json.dumps({"name": nom, "public": False,
                                           "description": "Trouvailles de Jarvis."}),
                          timeout=15)
        r.raise_for_status()
        _PLAYLIST_ID = r.json()["id"]
        return _PLAYLIST_ID


def _chercher_uri(titre, artiste):
    q = f"track:{titre} artist:{artiste}" if artiste else f"track:{titre}"
    r = requests.get(f"{_API}/search", headers=_h(),
                     params={"q": q, "type": "track", "limit": 1}, timeout=15)
    items = (r.json().get("tracks", {}) or {}).get("items", [])
    return items[0]["uri"] if items else None


def _deja_present(pid, uri):
    """Évite les doublons : l'URI est-elle déjà dans la playlist ?"""
    try:
        url = f"{_API}/playlists/{pid}/tracks?fields=items(track(uri)),next&limit=100"
        while url:
            d = requests.get(url, headers=_h(), timeout=15).json()
            for it in d.get("items", []):
                if ((it.get("track") or {}).get("uri")) == uri:
                    return True
            url = d.get("next")
    except Exception:
        pass
    return False


def _ajouter_titre(titre, artiste):
    """Ajoute (titre, artiste) à la playlist. Renvoie un message vocal."""
    if not (titre and str(titre).strip()):
        return "Je ne sais pas quelle musique ajouter."
    uri = _chercher_uri(titre, artiste)
    if not uri:
        return f"Je n'ai pas trouvé « {titre} » sur Spotify."
    pid = _playlist_id()
    if _deja_present(pid, uri):
        return f"« {titre} » est déjà dans la playlist."
    r = requests.post(f"{_API}/playlists/{pid}/tracks", headers=_h(),
                      data=json.dumps({"uris": [uri]}), timeout=15)
    r.raise_for_status()
    nom = reglage("spotify.playlist", "Jarvis Finds")
    return f"Ajoutée à {nom} : {titre}" + (f" de {artiste}." if artiste else ".")


# ------------------------------------------------------ auto-ajout (depuis musique)

def auto_ajouter(titre, artiste):
    """Appelé après une reconnaissance : ajoute en fond si spotify.auto_ajout."""
    if not reglage("spotify.auto_ajout", False) or not _configure():
        return
    def worker():
        try:
            _ajouter_titre(titre, artiste)
        except Exception:
            pass
    threading.Thread(target=worker, daemon=True, name="spotify-auto").start()


# ------------------------------------------------------ outils

@outil(
    nom="ajouter_a_playlist",
    description="Ajoute la DERNIÈRE musique reconnue (ou un titre donné) à ma playlist "
                "Spotify « Jarvis Finds ». Pour « ajoute-la à ma playlist », « mets "
                "cette chanson dans ma playlist », « ajoute ça à Spotify ».",
    parametres={
        "type": "object",
        "properties": {
            "titre": {"type": "string", "description": "Titre (optionnel ; vide = la "
                      "dernière musique reconnue)."},
            "artiste": {"type": "string", "description": "Artiste (optionnel)."},
        },
    },
    lent=True,
    phrase_attente="J'ajoute ça à ta playlist.",
    mcp_expose=False,
    affichage="jamais",
)
def ajouter_a_playlist(titre: str = "", artiste: str = "") -> str:
    if not _configure():
        return _msg_config()
    if not (titre and titre.strip()):
        try:
            from tools import musique
            derniere = musique.derniere_reconnaissance()
        except Exception:
            derniere = None
        if not derniere:
            return "Je n'ai pas de musique récente à ajouter. Dis d'abord « c'est quoi cette musique ? »."
        titre, artiste = derniere
    try:
        return _ajouter_titre(titre, artiste)
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", 0)
        if code == 403:
            return ("Spotify refuse l'accès (403) : soit le droit d'écriture des "
                    "playlists n'est pas accordé, soit l'app est en mode développement "
                    "avec un autre compte. Relance « python scripts/spotify_login.py » "
                    "et clique bien « Agree » sur l'écran des permissions.")
        return f"Spotify a échoué ({str(e)[:120]})."
    except Exception as e:
        return f"Spotify a échoué ({str(e)[:120]})."
