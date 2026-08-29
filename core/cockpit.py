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
import os
import shutil
import subprocess
import threading
import time
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


def _arreter_lowkey():
    """Coupe le moteur vocal puis demande l'arret propre de Lowkey."""
    if os.name == "nt":
        port = str(reglage("chatterbox.hote", "http://127.0.0.1:8004")).rsplit(":", 1)[-1]
        script = (f"$p=(Get-NetTCPConnection -LocalPort {int(port)} -State Listen "
                  "-ErrorAction SilentlyContinue | Select-Object -First 1 "
                  "-ExpandProperty OwningProcess); if($p){Stop-Process -Id $p -Force}")
        try:
            subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                            "-Command", script], timeout=8, check=False,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            LOG.exception("cockpit: arret du moteur vocal")
    from core.serveur import demander_arret
    demander_arret()


# ============================================================ fenêtre app

def _navigateur():
    chemin = reglage("cockpit.navigateur", "")
    if chemin and Path(chemin).exists():
        return chemin
    for nom in ("chrome", "msedge", "chromium"):
        exe = shutil.which(nom)
        if exe:
            return exe
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(p).exists():
            return p
    return None


def ouvrir_fenetre():
    """Ouvre le cockpit en fenêtre app (--app) sur l'écran choisi (cockpit.ecran)."""
    import time
    from core.serveur import _port, _port_ouvert
    for _ in range(40):                      # attend que le serveur écoute
        if _port_ouvert(_port()):
            break
        time.sleep(0.25)
    url = f"http://localhost:{_port()}/cockpit"
    exe = _navigateur()
    if not exe:
        import webbrowser
        webbrowser.open(url)
        return
    args = [exe, f"--app={url}", "--new-window"]
    try:
        import overlay
        rects = overlay._enum_moniteurs()
        idx = int(reglage("cockpit.ecran", 0))
        if rects and 0 <= idx < len(rects):
            l, t, _, _ = rects[idx]
            args += [f"--window-position={l + 40},{t + 40}", "--window-size=1280,860"]
    except Exception:
        pass
    try:
        subprocess.Popen(args)
        LOG.info("cockpit ouvert (%s)", url)
    except Exception:
        LOG.exception("cockpit: lancement navigateur")


# ============================================================ finances

_PERIODES = {                       # périodicité -> facteur vers le MENSUEL
    "mensuel": 1.0, "mois": 1.0,
    "annuel": 1 / 12, "an": 1 / 12, "annee": 1 / 12, "année": 1 / 12,
    "trimestriel": 1 / 3, "trimestre": 1 / 3,
    "semestriel": 1 / 6, "semestre": 1 / 6,
    "hebdomadaire": 52 / 12, "hebdo": 52 / 12, "semaine": 52 / 12,
}


def _facteur_mensuel(periodicite):
    return _PERIODES.get(sans_accents_min(periodicite), 1.0)


def sans_accents_min(s):
    from core.util import sans_accents
    return sans_accents(str(s or "").lower().strip())


def _ajouter_mois(d, n):
    m = d.month - 1 + n
    an = d.year + m // 12
    mois = m % 12 + 1
    jour = min(d.day, calendar.monthrange(an, mois)[1])
    return dt.date(an, mois, jour)


def _prochaine_echeance(abo, auj):
    """Prochaine date de prélèvement >= aujourd'hui."""
    per = sans_accents_min(abo.get("periodicite", "mensuel"))
    # date d'ancrage explicite ?
    ancre = abo.get("date")
    if ancre:
        try:
            d = dt.date.fromisoformat(str(ancre))
        except ValueError:
            d = None
        if d:
            pas = {"annuel": 12, "an": 12, "annee": 12, "année": 12,
                   "trimestriel": 3, "trimestre": 3, "semestriel": 6,
                   "semestre": 6}.get(per, 1)
            while d < auj:
                d = _ajouter_mois(d, pas)
            return d
    # sinon : jour du mois (mensuel par défaut)
    jour = int(abo.get("jour", 1) or 1)
    jour = max(1, min(jour, 28))
    d = dt.date(auj.year, auj.month, min(jour, calendar.monthrange(auj.year, auj.month)[1]))
    if d < auj:
        d = _ajouter_mois(d, 1)
    return d


def _charger_abonnements():
    if not _ABONNEMENTS.exists():
        return []
    try:
        data = yaml.safe_load(_ABONNEMENTS.read_text(encoding="utf-8")) or []
        return [a for a in data if isinstance(a, dict) and a.get("service")]
    except Exception:
        LOG.exception("cockpit: lecture abonnements")
        return []


def _detecter_changements(abos):
    """Compare les montants aux derniers vus (persistés) -> alertes « montant changé »."""
    anciens = {}
    if _ETAT_ABO.exists():
        try:
            anciens = json.loads(_ETAT_ABO.read_text(encoding="utf-8")) or {}
        except Exception:
            anciens = {}
    changements, actuels = [], {}
    for a in abos:
        nom = str(a.get("service"))
        montant = float(a.get("montant", 0) or 0)
        actuels[nom] = montant
        if nom in anciens and abs(anciens[nom] - montant) > 0.001:
            changements.append({"service": nom, "avant": anciens[nom], "apres": montant})
    try:
        _DOSSIER.mkdir(parents=True, exist_ok=True)
        _ETAT_ABO.write_text(json.dumps(actuels, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return changements


def _finances():
    auj = dt.date.today()
    abos = _charger_abonnements()
    enrichis, total, par_cat = [], 0.0, {}
    for a in abos:
        montant = float(a.get("montant", 0) or 0)
        mensuel = round(montant * _facteur_mensuel(a.get("periodicite", "mensuel")), 2)
        total += mensuel
        cat = str(a.get("categorie", "Autres"))
        par_cat[cat] = round(par_cat.get(cat, 0.0) + mensuel, 2)
        prochaine = _prochaine_echeance(a, auj)
        enrichis.append({
            "service": a.get("service"), "montant": montant,
            "periodicite": a.get("periodicite", "mensuel"),
            "mensuel": mensuel, "categorie": cat,
            "prochaine": prochaine.isoformat(),
            "dans_jours": (prochaine - auj).days,
        })
    enrichis.sort(key=lambda x: x["prochaine"])
    demain = auj + dt.timedelta(days=1)
    alertes = [f"Prélèvement demain : {e['service']} ({e['montant']:.2f} €)"
               for e in enrichis if e["prochaine"] == demain.isoformat()]
    for c in _detecter_changements(abos):
        alertes.append(f"Montant changé : {c['service']} {c['avant']:.2f} € → {c['apres']:.2f} €")
    return {
        "total_mensuel": round(total, 2),
        "total_annuel": round(total * 12, 2),
        "par_categorie": par_cat,
        "abonnements": enrichis,
        "alertes": alertes,
        "nb": len(enrichis),
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

    @app.get("/api/cockpit/interactions")
    def api_interactions(request: Request, limite: int = 100):
        if (r := garde(request)):
            return r
        from core.interactions import lire
        return {"interactions": lire(limite)}

    @app.post("/api/cockpit/stop")
    def api_stop(request: Request):
        if (r := garde(request)):
            return r
        if request.headers.get("x-lowkey-action") != "stop":
            return JSONResponse({"ok": False, "message": "Confirmation requise."},
                                status_code=400)
        threading.Thread(target=lambda: (time.sleep(0.6), _arreter_lowkey()),
                         daemon=True, name="arret-lowkey").start()
        return {"ok": True, "message": "Arrêt de Lowkey en cours."}

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
