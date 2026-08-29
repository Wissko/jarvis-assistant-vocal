"""Historique local et prive des echanges vocaux avec Lowkey."""
import datetime as dt
import json
import threading
from collections import deque
from pathlib import Path


_FICHIER = Path(__file__).resolve().parent.parent / "logs" / "interactions.jsonl"
_VERROU = threading.Lock()


def ajouter(role, texte, langue=""):
    """Ajoute une interaction textuelle au journal JSONL local."""
    texte = str(texte or "").strip()
    if role not in {"user", "assistant"} or not texte:
        return
    entree = {
        "timestamp": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "role": role,
        "texte": texte,
        "langue": str(langue or "").lower()[:5],
    }
    with _VERROU:
        _FICHIER.parent.mkdir(parents=True, exist_ok=True)
        with _FICHIER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entree, ensure_ascii=False) + "\n")


def lire(limite=100):
    """Renvoie les dernieres interactions, de la plus ancienne a la plus recente."""
    limite = max(1, min(int(limite or 100), 500))
    if not _FICHIER.exists():
        return []
    lignes = deque(maxlen=limite)
    with _VERROU:
        try:
            with _FICHIER.open("r", encoding="utf-8") as f:
                for ligne in f:
                    lignes.append(ligne)
        except OSError:
            return []
    resultat = []
    for ligne in lignes:
        try:
            entree = json.loads(ligne)
            if entree.get("role") in {"user", "assistant"} and entree.get("texte"):
                resultat.append(entree)
        except (TypeError, ValueError):
            continue
    return resultat
