"""Budget : suivi de la consommation LLM de Jarvis, par jour et par fournisseur.

Jarvis instrumente ses PROPRES appels Claude (tokens in/out + cache) et estime le
cout via une table de prix configurable (budget.prix), persiste dans budget.json
(non versionne). La page Etat du panneau lit resume() (jour + mois), et croise avec
le compteur Twilio (logs/calls/compteur.json) et les insights Hermes (CLI).

Hermes tient sa propre comptabilite (hermes insights) : Jarvis ne double pas.
"""
import datetime as dt
import json
import logging
import threading
from pathlib import Path

from core.config import reglage

LOG = logging.getLogger("jarvis")
_RACINE = Path(__file__).resolve().parent.parent
_VERROU = threading.Lock()

# Prix par defaut ($ / million de tokens : entree, sortie). Surchargeables via
# config budget.prix. Cle = sous-chaine du nom de modele (tarifs API Anthropic).
_PRIX_DEFAUT = {
    "haiku": (1.0, 5.0),
    "sonnet": (3.0, 15.0),
    "opus": (5.0, 25.0),
}


def _fichier():
    return _RACINE / "budget.json"


def _charger():
    f = _fichier()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def _prix(modele):
    """(prix_entree, prix_sortie) $/Mtok pour un modele, via la plus longue cle qui matche."""
    m = (modele or "").lower()
    conf = reglage("budget.prix", {}) or {}
    for cle in sorted(set(list(conf) + list(_PRIX_DEFAUT)), key=len, reverse=True):
        if cle.lower() in m:
            v = conf.get(cle) if conf.get(cle) is not None else _PRIX_DEFAUT.get(cle)
            if isinstance(v, (list, tuple)) and len(v) == 2:
                return float(v[0]), float(v[1])
    return 0.0, 0.0


def enregistrer(fournisseur, modele, tin, tout, cache_read=0, cache_creation=0):
    """Ajoute la conso d'un appel LLM au budget du jour. Cout precis (cache read 0.1x,
    cache creation 1.25x, tarifs Anthropic)."""
    try:
        pin, pout = _prix(modele)
        cout = (int(tin or 0) * pin
                + int(cache_creation or 0) * pin * 1.25
                + int(cache_read or 0) * pin * 0.1
                + int(tout or 0) * pout) / 1e6
        total_in = int(tin or 0) + int(cache_read or 0) + int(cache_creation or 0)
        jour = dt.date.today().isoformat()
        with _VERROU:
            data = _charger()
            j = data.setdefault(jour, {})
            f = j.setdefault(fournisseur,
                             {"modele": modele, "appels": 0, "tin": 0, "tout": 0, "cout": 0.0})
            f["modele"] = modele
            f["appels"] += 1
            f["tin"] += total_in
            f["tout"] += int(tout or 0)
            f["cout"] = round(f["cout"] + cout, 4)
            _fichier().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        LOG.exception("budget: enregistrement")


def _agreger(data, prefixe):
    """Somme par fournisseur sur toutes les dates commencant par prefixe (jour ou mois)."""
    total = {}
    for jour, parj in data.items():
        if not str(jour).startswith(prefixe):
            continue
        for fourn, v in parj.items():
            t = total.setdefault(fourn, {"modele": v.get("modele", ""), "appels": 0,
                                         "tin": 0, "tout": 0, "cout": 0.0})
            t["appels"] += v.get("appels", 0)
            t["tin"] += v.get("tin", 0)
            t["tout"] += v.get("tout", 0)
            t["cout"] = round(t["cout"] + v.get("cout", 0.0), 4)
    return total


def resume():
    """{jour: {fournisseur: {...}}, mois: {...}} de la conso LLM de Jarvis."""
    data = _charger()
    auj = dt.date.today()
    return {"jour": _agreger(data, auj.isoformat()),
            "mois": _agreger(data, auj.strftime("%Y-%m"))}
