"""Cockpit : app web locale (servie par le serveur unifié) — tableau de bord perso.

DOCTRINE : Jarvis détient les clés et le corps ; TOUTES les données restent LOCALES
(dossier finances/ gitignoré). Rien n'est exposé au MCP ni au réseau : garde
local-only (comme le panneau). Hermes ne reçoit que des AGRÉGATS, sur demande.

Phase 1 : la fondation + le volet FINANCES (abonnements.yaml -> total mensuel,
timeline des échéances, alertes « prélèvement demain » / « montant changé »).
Volets Énergie / Réseaux / Contenu / Maison à venir. Voir docs/cockpit.md.
"""
import calendar
import datetime as dt
import json
import logging
import shutil
import subprocess
import urllib.request
from pathlib import Path

import yaml

from core.config import reglage
from core.panneau import _local_seulement   # même garde local que le panneau

LOG = logging.getLogger("jarvis")
_RACINE = Path(__file__).resolve().parent.parent
_HTML = _RACINE / "web" / "cockpit.html"
_DOSSIER = _RACINE / "finances"
_ABONNEMENTS = _DOSSIER / "abonnements.yaml"
_ETAT_ABO = _DOSSIER / ".etat_abonnements.json"   # pour détecter « montant changé »
_BUSINESSES = _RACINE / "businesses.yaml"
_BUSINESSES_EXEMPLE = _RACINE / "businesses.example.yaml"


def _charger_activites():
    """Charge le portefeuille personnel local sans jamais l'exposer hors du PC."""
    source = _BUSINESSES if _BUSINESSES.exists() else _BUSINESSES_EXEMPLE
    try:
        donnees = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except Exception:
        LOG.exception("cockpit: lecture businesses.yaml")
        donnees = {}
    profil = donnees.get("profil") if isinstance(donnees.get("profil"), dict) else {}
    domaines = donnees.get("domaines") if isinstance(donnees.get("domaines"), list) else []
    nettoyes = []
    for domaine in domaines:
        if not isinstance(domaine, dict):
            continue
        projets = [p for p in (domaine.get("projets") or [])
                   if isinstance(p, dict) and p.get("nom")]
        nettoyes.append({
            "id": str(domaine.get("id") or "domaine"),
            "nom": str(domaine.get("nom") or "Activité"),
            "description": str(domaine.get("description") or ""),
            "projets": projets,
        })
    return {"profil": profil, "domaines": nettoyes,
            "total_projets": sum(len(d["projets"]) for d in nettoyes)}


def _etat_lowkey():
    activites = _charger_activites()
    chatterbox = {"ok": False, "modele": "hors ligne", "device": "—"}
    hote = str(reglage("chatterbox.hote", "http://127.0.0.1:8004")).rstrip("/")
    try:
        with urllib.request.urlopen(f"{hote}/api/model-info", timeout=1.2) as reponse:
            info = json.loads(reponse.read().decode("utf-8"))
        chatterbox = {"ok": bool(info.get("loaded")),
                      "modele": info.get("type") or "Chatterbox",
                      "device": info.get("device") or "—"}
    except Exception:
        pass
    return {
        "assistant": str(reglage("assistant.nom", "Lowkey")),
        "mode": str(reglage("mode", "hybride")),
        "chatterbox": chatterbox,
        "domaines": len(activites["domaines"]),
        "projets": activites["total_projets"],
        "local": True,
    }


def _charger_activites():
    """Charge le portefeuille personnel local sans jamais l'exposer hors du PC."""
    source = _BUSINESSES if _BUSINESSES.exists() else _BUSINESSES_EXEMPLE
    try:
        donnees = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except Exception:
        LOG.exception("cockpit: lecture businesses.yaml")
        donnees = {}
    profil = donnees.get("profil") if isinstance(donnees.get("profil"), dict) else {}
    domaines = donnees.get("domaines") if isinstance(donnees.get("domaines"), list) else []
    nettoyes = []
    for domaine in domaines:
        if not isinstance(domaine, dict):
            continue
        projets = [p for p in (domaine.get("projets") or [])
                   if isinstance(p, dict) and p.get("nom")]
        nettoyes.append({
            "id": str(domaine.get("id") or "domaine"),
            "nom": str(domaine.get("nom") or "Activité"),
            "description": str(domaine.get("description") or ""),
            "projets": projets,
        })
    return {"profil": profil, "domaines": nettoyes,
            "total_projets": sum(len(d["projets"]) for d in nettoyes)}


def _etat_lowkey():
    activites = _charger_activites()
    chatterbox = {"ok": False, "modele": "hors ligne", "device": "—"}
    hote = str(reglage("chatterbox.hote", "http://127.0.0.1:8004")).rstrip("/")
    try:
        with urllib.request.urlopen(f"{hote}/api/model-info", timeout=1.2) as reponse:
            info = json.loads(reponse.read().decode("utf-8"))
        chatterbox = {"ok": bool(info.get("loaded")),
                      "modele": info.get("type") or "Chatterbox",
                      "device": info.get("device") or "—"}
    except Exception:
        pass
    return {
        "assistant": str(reglage("assistant.nom", "Lowkey")),
        "mode": str(reglage("mode", "hybride")),
        "chatterbox": chatterbox,
        "domaines": len(activites["domaines"]),
        "projets": activites["total_projets"],
        "local": True,
    }


# ============================================================ routes

def monter_routes(app):
    from fastapi import Request
    from fastapi.responses import HTMLResponse, JSONResponse

    def garde(request: Request):
        if not _local_seulement(request):
            return JSONResponse({"ok": False, "message": "Cockpit local uniquement."},
                                status_code=403)
        return None

    @app.get("/")
    @app.get("/cockpit")
    def cockpit(request: Request):
        refus = garde(request)
        if refus:
            return refus
        if not _HTML.exists():
            return HTMLResponse("<h1>Cockpit</h1><p>web/cockpit.html manquant.</p>", 500)
        return HTMLResponse(_HTML.read_text(encoding="utf-8"))

    @app.get("/api/cockpit/activites")
    def api_activites(request: Request):
        return garde(request) or _charger_activites()

    @app.get("/api/cockpit/status")
    def api_status(request: Request):
        return garde(request) or _etat_lowkey()

    @app.get("/api/cockpit/finances")
    def api_finances(request: Request):
        return garde(request) or _finances()

    @app.get("/api/cockpit/status")
    def api_status(request: Request):
        return garde(request) or _etat_lowkey()

    @app.get("/api/cockpit/finances")
    def api_finances(request: Request):
        return garde(request) or _finances()

    @app.get("/api/cockpit/transactions")
    def api_transactions(request: Request, mois: str = ""):
        if (r := garde(request)):
            return r
        from core import transactions as tx
        return {"vue": tx.vue_mois(mois or None),
                "recurrents": tx.abonnements_recurrents()}

    LOG.info("cockpit monte : /cockpit (local uniquement)")

