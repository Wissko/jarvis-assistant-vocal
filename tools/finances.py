"""Détection d'abonnements par mail (Gmail IMAP déjà configuré) — alimente le
cockpit Finances SANS credential bancaire ni API d'agrégation (doctrine).

Flux : on scanne les REÇUS des derniers mois, on en déduit service + montant +
périodicité (règles + annuaire de services connus), on écrit une proposition dans
finances/abonnements_detectes.yaml (REVUE, jamais écrasement direct), puis on
intègre dans abonnements.yaml UNIQUEMENT sur confirmation. Tout reste local.

N1 pour la détection (lecture + fichier de revue) ; N2 (confirmation) pour
l'intégration. Non exposé au MCP. Voir docs/cockpit.md.
"""
import datetime as dt
import imaplib
import re
from pathlib import Path

import yaml

from core.config import reglage
from core.registre import outil

# Réutilise la config Gmail du module mail.
from tools.mail import (IMAP_SERVEUR, MAIL_ADRESSE, _corps_texte, _decoder_entete,
                        _mail_configure, _mail_mdp)

_RACINE = Path(__file__).resolve().parent.parent
_DOSSIER = _RACINE / "finances"
_ABONNEMENTS = _DOSSIER / "abonnements.yaml"
_DETECTES = _DOSSIER / "abonnements_detectes.yaml"

# Annuaire : sous-chaîne du domaine expéditeur -> (service, catégorie).
_SERVICES = {
    "apple.com": ("Apple", "Abonnements"), "itunes.com": ("Apple", "Abonnements"),
    "netflix.com": ("Netflix", "Streaming"), "spotify.com": ("Spotify", "Musique"),
    "adobe.com": ("Adobe", "Logiciels"), "disney": ("Disney+", "Streaming"),
    "youtube.com": ("YouTube Premium", "Streaming"), "deezer.com": ("Deezer", "Musique"),
    "canal": ("Canal+", "Streaming"), "microsoft.com": ("Microsoft 365", "Logiciels"),
    "openai.com": ("ChatGPT", "Logiciels"), "anthropic.com": ("Claude", "Logiciels"),
    "notion.so": ("Notion", "Logiciels"), "dropbox.com": ("Dropbox", "Cloud"),
    "amazon": ("Amazon Prime", "Abonnements"), "paramount": ("Paramount+", "Streaming"),
    "twitch.tv": ("Twitch", "Streaming"), "patreon.com": ("Patreon", "Abonnements"),
    "molotov": ("Molotov", "Streaming"), "audible": ("Audible", "Abonnements"),
    "linkedin.com": ("LinkedIn Premium", "Logiciels"), "github.com": ("GitHub", "Logiciels"),
    "figma.com": ("Figma", "Logiciels"), "google.com": ("Google One", "Cloud"),
}

_MOTS_ANNUEL = ("par an", "/an", "annuel", "yearly", "per year", "année", "annual")
_MONTANT = re.compile(r"(\d{1,4}[.,]\d{2})\s*(?:€|eur)|(?:€|eur)\s*(\d{1,4}[.,]\d{2})",
                      re.IGNORECASE)


def _service_depuis(exp_adresse, sujet):
    dom = exp_adresse.lower()
    for cle, (nom, cat) in _SERVICES.items():
        if cle in dom:
            return nom, cat
    # sinon : nom du domaine (2e niveau) capitalisé
    m = re.search(r"@([\w-]+)\.", exp_adresse)
    base = (m.group(1) if m else (sujet.split()[0] if sujet else "Abonnement"))
    return base.capitalize(), "Autres"


def _montant(texte):
    """Le montant le plus plausible : proche de 'total', sinon le plus grand < 500."""
    cands = []
    for m in _MONTANT.finditer(texte):
        val = (m.group(1) or m.group(2) or "").replace(",", ".")
        try:
            v = float(val)
        except ValueError:
            continue
        if 0.5 <= v <= 2000:                     # jusqu'aux abonnements annuels
            # bonus si "total"/"montant" dans les 40 caractères précédents
            avant = texte[max(0, m.start() - 40):m.start()].lower()
            prio = 2 if ("total" in avant or "montant" in avant or "débité" in avant) else 1
            cands.append((prio, v))
    if not cands:
        return None
    cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return cands[0][1]


def _scanner(mois):
    """Renvoie {service: {montant, periodicite, jour, categorie, date}} le plus récent."""
    trouves = {}
    imap = imaplib.IMAP4_SSL(IMAP_SERVEUR)
    imap.login(MAIL_ADRESSE, _mail_mdp())
    try:
        imap.select("INBOX")
        requete = (f'(subject:(reçu OR receipt OR abonnement OR subscription OR '
                   f'renouvellement OR renewal OR facture OR invoice OR paiement OR '
                   f'payment)) newer_than:{int(mois)}m')
        typ, donnees = imap.uid("search", None, "X-GM-RAW", requete)
        ids = donnees[0].split() if donnees and donnees[0] else []
        import email as emod
        for num in ids[-200:]:                       # borne de sécurité
            _, d = imap.uid("fetch", num, "(BODY.PEEK[])")
            if not d or not d[0]:
                continue
            msg = emod.message_from_bytes(d[0][1])
            exp = _decoder_entete(msg.get("From", ""))
            adresse = re.search(r"[\w.+-]+@[\w.-]+", exp)
            adresse = adresse.group(0) if adresse else exp
            sujet = _decoder_entete(msg.get("Subject", ""))
            corps = _corps_texte(msg) or ""
            montant = _montant(sujet + "\n" + corps)
            if montant is None:
                continue
            service, cat = _service_depuis(adresse, sujet)
            per = "annuel" if any(x in (sujet + corps).lower() for x in _MOTS_ANNUEL) \
                else "mensuel"
            # date du mail -> jour du prélèvement
            try:
                da = emod.utils.parsedate_to_datetime(msg.get("Date"))
                jour = da.day
                iso = da.date().isoformat()
            except Exception:
                jour, iso = 1, ""
            # garde la détection la PLUS RÉCENTE par service
            if service not in trouves or iso > trouves[service].get("date", ""):
                trouves[service] = {"service": service, "montant": montant,
                                    "periodicite": per, "jour": jour,
                                    "categorie": cat, "date": iso}
        return trouves
    finally:
        try:
            imap.logout()
        except Exception:
            pass


@outil(
    nom="detecter_abonnements",
    description="Cherche mes abonnements dans mes mails (reçus Apple, Netflix, Spotify, "
                "Adobe…) et propose de mettre à jour le cockpit. Pour « détecte mes "
                "abonnements », « cherche mes abonnements dans mes mails », « scanne "
                "mes reçus ». N'écrit rien dans mes abonnements sans confirmation.",
    parametres={
        "type": "object",
        "properties": {
            "mois": {"type": "integer",
                     "description": "Profondeur de recherche en mois (défaut 6)."}
        },
    },
    lent=True,
    phrase_attente="Je fouille tes reçus dans tes mails.",
    mcp_expose=False,
    affichage="toujours",
)
def detecter_abonnements(mois: int = 6) -> str:
    if not _mail_configure():
        return "La messagerie n'est pas configurée (mail.adresse / mot de passe d'app)."
    try:
        trouves = _scanner(max(1, min(int(mois or 6), 24)))
    except Exception as e:
        return f"Le scan des mails a échoué ({str(e)[:120]})."
    if not trouves:
        return "Je n'ai trouvé aucun reçu d'abonnement dans tes mails récents."
    _DOSSIER.mkdir(parents=True, exist_ok=True)
    liste = sorted(trouves.values(), key=lambda x: -x["montant"])
    _DETECTES.write_text(yaml.safe_dump(liste, allow_unicode=True, sort_keys=False),
                         encoding="utf-8")
    apercu = ", ".join(f"{a['service']} {a['montant']:.2f}€" for a in liste[:6])
    suite = "" if len(liste) <= 6 else f" et {len(liste) - 6} autres"
    return (f"J'ai trouvé {len(liste)} abonnements : {apercu}{suite}. Ils sont dans "
            "abonnements_detectes.yaml. Dis « intègre-les » pour les ajouter au cockpit.")


@outil(
    nom="integrer_abonnements_detectes",
    description="Ajoute au cockpit les abonnements détectés dans les mails (fichier de "
                "revue abonnements_detectes.yaml). Pour « intègre-les », « ajoute les "
                "abonnements détectés », « valide mes abonnements ».",
    confirmation=True,
    annonce=lambda a: "Je vais ajouter les abonnements détectés à ton cockpit.",
    mcp_expose=False,
)
def integrer_abonnements_detectes() -> str:
    if not _DETECTES.exists():
        return "Aucune détection en attente. Lance d'abord « détecte mes abonnements »."
    detectes = yaml.safe_load(_DETECTES.read_text(encoding="utf-8")) or []
    existants = []
    if _ABONNEMENTS.exists():
        existants = yaml.safe_load(_ABONNEMENTS.read_text(encoding="utf-8")) or []
    noms = {str(a.get("service", "")).lower() for a in existants if isinstance(a, dict)}
    ajoutes = 0
    for a in detectes:
        if str(a.get("service", "")).lower() in noms:
            continue                                 # ne remplace pas un existant manuel
        existants.append({k: a[k] for k in ("service", "montant", "periodicite",
                                            "jour", "categorie") if k in a})
        ajoutes += 1
    _ABONNEMENTS.write_text(yaml.safe_dump(existants, allow_unicode=True, sort_keys=False),
                            encoding="utf-8")
    if not ajoutes:
        return "Tous les abonnements détectés étaient déjà dans ton cockpit."
    return f"C'est fait, j'ai ajouté {ajoutes} abonnement(s) au cockpit."
