"""Precharge silencieusement les deux voix Chatterbox au demarrage de Lowkey."""
import json
import time
import urllib.request

from core.config import reglage


def _attendre_serveur(hote, delai=90):
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(f"{hote}/api/model-info", timeout=2) as reponse:
                if json.loads(reponse.read()).get("loaded"):
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def _charger(hote, voix, langue, texte, vitesse, seed):
    charge = json.dumps({
        "model": "chatterbox-multilingual",
        "input": texte,
        "voice": voix,
        "response_format": "wav",
        "speed": vitesse,
        "seed": seed,
        "language": langue,
    }).encode("utf-8")
    requete = urllib.request.Request(
        f"{hote}/v1/audio/speech", data=charge, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(requete, timeout=120) as reponse:
        reponse.read()


def main():
    # XTTS charge deja le modele et les deux empreintes avant d'ouvrir son port.
    if reglage("xtts.actif", False):
        hote = str(reglage("xtts.hote", "http://127.0.0.1:8020")).rstrip("/")
        limite = time.monotonic() + float(reglage("xtts.timeout", 180))
        while time.monotonic() < limite:
            try:
                with urllib.request.urlopen(f"{hote}/health", timeout=2):
                    return
            except Exception:
                time.sleep(2)
        return
    if not reglage("chatterbox.actif", False):
        return
    hote = str(reglage("chatterbox.hote", "http://127.0.0.1:8004")).rstrip("/")
    if not _attendre_serveur(hote):
        return
    vitesse = float(reglage("chatterbox.vitesse", 1.08))
    seed = int(reglage("chatterbox.seed", 108))
    voix = (
        (str(reglage("chatterbox.voix_fr", "Lowkey-FR-Valet.wav")), "fr", "Bien entendu."),
        (str(reglage("chatterbox.voix_en", "Henry.wav")), "en", "Certainly."),
    )
    for nom, langue, texte in voix:
        try:
            _charger(hote, nom, langue, texte, vitesse, seed)
        except Exception:
            pass


if __name__ == "__main__":
    main()
