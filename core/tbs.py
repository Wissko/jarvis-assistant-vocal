"""Contexte métier TBS pour Lowkey, statique et synchronisé avec le CRM."""
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from core.config import reglage

_RACINE = Path(__file__).resolve().parent.parent
_CACHE = {"at": 0.0, "data": None, "error": ""}
_LOCK = threading.Lock()


def _ecosysteme():
    for nom in ("businesses.yaml", "businesses.example.yaml"):
        chemin = _RACINE / nom
        try:
            donnees = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
            if donnees:
                return donnees
        except (OSError, yaml.YAMLError):
            continue
    return {}


def contexte_statique():
    """Carte compacte des activités, assez stable pour la consigne système."""
    donnees = _ecosysteme()
    domaines = []
    for domaine in donnees.get("domaines", []):
        projets = ", ".join(
            f"{p.get('nom')} ({p.get('type')})"
            for p in domaine.get("projets", []) if p.get("nom")
        )
        domaines.append(
            f"- {domaine.get('nom', 'Domaine')}: {domaine.get('description', '')} "
            f"Projets: {projets}."
        )
    if not domaines:
        return ""
    return (
        "\n\nCONTEXTE METIER PERMANENT (portefeuille de Yose):\n"
        "TBS / TO BE SEEN est son agence et TBS Workspace est la source de vérité "
        "opérationnelle. Howard CRM est un système séparé et ne doit pas être confondu "
        "avec TBS Workspace.\n" + "\n".join(domaines)
    )


def _configuration():
    url = str(reglage("tbs.api_url", "") or "").strip().rstrip("/")
    token = str(reglage("tbs.service_token", "") or "").strip()
    timeout = float(reglage("tbs.timeout", 6) or 6)
    return url, token, max(1.0, min(timeout, 30.0))


def _appel(method="GET", payload=None):
    url, token, timeout = _configuration()
    if not url or not token:
        raise RuntimeError("connexion TBS non configurée")
    donnees = None if payload is None else json.dumps(payload).encode("utf-8")
    requete = urllib.request.Request(
        url,
        data=donnees,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Lowkey-TBS/1.0",
        },
    )
    try:
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            return json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", "")
        except Exception:
            detail = ""
        raise RuntimeError(detail or f"TBS HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"TBS indisponible: {exc}") from exc


def instantane(force=False):
    """Lit le CRM avec un petit cache pour ne pas ralentir chaque réponse vocale."""
    ttl = max(5, int(reglage("tbs.cache_seconds", 45) or 45))
    with _LOCK:
        if not force and _CACHE["data"] is not None and time.monotonic() - _CACHE["at"] < ttl:
            return _CACHE["data"], ""
        try:
            donnees = _appel()
            _CACHE.update(at=time.monotonic(), data=donnees, error="")
            return donnees, ""
        except RuntimeError as exc:
            _CACHE.update(at=time.monotonic(), error=str(exc))
            return _CACHE["data"], str(exc)


def _liste(donnees, cle, champs, maximum):
    lignes = []
    for item in (donnees.get(cle) or [])[:maximum]:
        morceaux = [str(item.get(champ)) for champ in champs if item.get(champ) not in (None, "")]
        if morceaux:
            lignes.append(" / ".join(morceaux))
    return "; ".join(lignes) or "aucun"


def formater(donnees):
    if not donnees:
        return ""
    metriques = donnees.get("metrics") or {}
    return (
        "DONNEES TBS WORKSPACE ACTUELLES (faits issus du CRM):\n"
        f"- Indicateurs: {metriques.get('clients', 0)} clients; "
        f"{metriques.get('projects', 0)} projets; {metriques.get('openTasks', 0)} tâches ouvertes; "
        f"{metriques.get('unpaidInvoices', 0)} factures impayées; "
        f"{metriques.get('activeSubscriptions', 0)} abonnements actifs.\n"
        f"- Encours par devise: {metriques.get('outstandingByCurrency', {})}. MRR par devise: {metriques.get('monthlyRecurringByCurrency', {})}.\n"
        f"- Projets: {_liste(donnees, 'projects', ('name', 'status', 'priority', 'end_date'), 18)}.\n"
        f"- Priorités/tâches: {_liste(donnees, 'openTasks', ('name', 'project', 'priority', 'due_date'), 20)}.\n"
        f"- Factures à suivre: {_liste(donnees, 'unpaidInvoices', ('name', 'client', 'status', 'amount', 'currency', 'due_date'), 12)}.\n"
        f"- Prochains rendez-vous: {_liste(donnees, 'upcomingMeetings', ('name', 'client', 'meeting_date', 'starts_at'), 10)}.\n"
        f"- Notes récentes: {_liste(donnees, 'recentNotes', ('name', 'project', 'body'), 8)}."
    )


def contexte_dynamique():
    donnees, _ = instantane()
    texte = formater(donnees)
    return f"\n\n{texte}" if texte else ""


def executer_action(payload):
    resultat = _appel("POST", payload)
    _CACHE.update(at=0.0, data=None, error="")
    return resultat
