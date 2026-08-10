"""Serveur web unifie de Jarvis : UN seul FastAPI / UN seul port pour tout.

Regroupe, sous un unique tunnel ngrok :
  - le pont iPhone      -> POST /api/inbox        (core.pont_iphone)
  - le webhook Twilio   -> WebSocket /stream      (tools.appel_direct, appels V2)
  - les futures PWA     -> a monter ici (routes /...)

Ainsi ton domaine ngrok statique sert TOUT. Config : section `serveur`
(actif/port/public_url/ngrok_authtoken). Les anciennes cles (pont_iphone.port,
twilio.public_url/ngrok_authtoken, appels.port_stream) restent lues en repli.
"""
import logging
import socket
import threading

from core.config import reglage

LOG = logging.getLogger("jarvis")

_APP = None
_SERVEUR = None
_URL = None


def _port():
    return int(reglage("serveur.port",
                       reglage("pont_iphone.port", reglage("appels.port_stream", 8790))))


def app():
    """Construit (une fois) l'app FastAPI avec toutes les routes montees."""
    global _APP
    if _APP is None:
        from fastapi import FastAPI
        _APP = FastAPI(title="Jarvis")
        from core.pont_iphone import monter_routes
        monter_routes(_APP)                       # /api/inbox, /api/ping
        try:
            from tools.appel_direct import monter_ws
            monter_ws(_APP)                        # /stream (Twilio Media Streams)
        except Exception:
            LOG.exception("montage du websocket /stream")
    return _APP


def _port_ouvert(port, timeout=0.3):
    try:
        socket.create_connection(("127.0.0.1", port), timeout).close()
        return True
    except OSError:
        return False


def demarrer():
    """Lance le serveur unifie en tache de fond (idempotent). Attend qu'il ecoute."""
    global _SERVEUR
    port = _port()
    if _SERVEUR and _SERVEUR.is_alive():
        return
    import time
    import uvicorn
    config = uvicorn.Config(app(), host="0.0.0.0", port=port, log_level="warning")
    serveur = uvicorn.Server(config)

    def run():
        try:
            serveur.run()   # uvicorn n'installe pas les handlers de signaux hors main thread
        except Exception:
            LOG.exception("serveur web")

    _SERVEUR = threading.Thread(target=run, daemon=True, name="serveur-web")
    _SERVEUR.start()
    for _ in range(40):                # attend l'ouverture du port (max ~6 s)
        if _port_ouvert(port):
            break
        time.sleep(0.15)
    print(f"Serveur web : port {port} (iPhone /api/inbox, Twilio /stream). "
          "Expose ce port via ton ngrok statique.")


def url_publique():
    """Base publique https:// : ton domaine ngrok statique, ou un tunnel auto."""
    global _URL
    manuel = reglage("serveur.public_url", "") or reglage("twilio.public_url", "")
    if manuel:
        return manuel.rstrip("/")
    if _URL:
        return _URL
    from pyngrok import ngrok
    tok = reglage("serveur.ngrok_authtoken", "") or reglage("twilio.ngrok_authtoken", "")
    if tok:
        ngrok.set_auth_token(tok)
    _URL = ngrok.connect(_port(), "http").public_url
    LOG.info("tunnel ngrok : %s", _URL)
    return _URL


def url_ws():
    """Base wss:// (pour l'URL du <Stream> de Twilio)."""
    return url_publique().replace("https://", "wss://").replace("http://", "ws://")
