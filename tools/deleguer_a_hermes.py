"""Delegation d'une tache a Hermes Agent (cerveau delibératif) via son API locale.

Flux : Jarvis envoie la tache a l'API d'Hermes (gateway loopback 8642), repond
TOUT DE SUITE "je delegue, je te previens", puis - en tache de fond - recupere le
resultat, le passe au FILTRE DE CONFIDENTIALITE, et l'annonce a voix haute (resume
court). Session persistante entre delegations (parametre `conversation`).

Securite :
- NON expose via MCP (mcp_expose defaut False) : un agent externe ne peut pas
  declencher de delegation.
- confirmation vocale requise (une delegation peut couter et durer).
- le resultat lu a voix haute passe par core.confidentialite.filtrer().
Voir docs/hermes.md.
"""
import threading
from pathlib import Path

from core import voix, confidentialite
from core.config import reglage
from core.registre import outil

# Magasin de certificats Windows (Malwarebytes/AV) puis requests.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass
import requests

# --- suivi HUD : tâches Hermes en cours + part Hermes (tokens) ---
_EN_COURS = 0
_LOCK = threading.Lock()
_TOKENS = None


def taches_en_cours() -> int:
    return _EN_COURS


def _pousser_hud():
    try:
        import hud
        hud.hermes(_EN_COURS, _TOKENS)
    except Exception:
        pass


def _maj_tokens():
    global _TOKENS
    try:
        import re
        import shutil
        import subprocess
        exe = shutil.which("hermes")
        if not exe:
            return
        p = subprocess.run([exe, "insights", "--days", "30"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=60)
        m = re.search(r"Total tokens:\s+([\d,]+)", (p.stdout or "") + (p.stderr or ""))
        if m:
            _TOKENS = int(m.group(1).replace(",", ""))
    except Exception:
        pass


def rafraichir_hud():
    """Rafraîchit la part Hermes (tokens) puis pousse au HUD. Appelé au démarrage."""
    _maj_tokens()
    _pousser_hud()


def _cle_api() -> str:
    """Cle API du serveur Hermes : config.yaml hermes.api_key, sinon fichier."""
    cle = reglage("hermes.api_key", "")
    if cle:
        return cle
    chemin = reglage("hermes.api_key_file", "")
    if chemin:
        try:
            contenu = Path(chemin).read_text(encoding="utf-8").strip()
            return contenu.split("=", 1)[-1].strip()   # gere "API_SERVER_KEY=xxx"
        except Exception:
            pass
    return ""


def _appeler_hermes(tache: str) -> str:
    base = reglage("hermes.api_url", "http://127.0.0.1:8642").rstrip("/")
    cle = _cle_api()
    if not cle:
        raise RuntimeError("cle API Hermes introuvable (hermes.api_key)")
    prompt = (
        f"{tache}\n\n"
        "IMPORTANT : effectue la tache MAINTENANT et renvoie la reponse COMPLETE et "
        "definitive dans CE meme message. N'annonce PAS que tu vas le faire, ne dis "
        "pas 'un instant'. Reponds en francais. Termine IMPERATIVEMENT par une "
        "derniere ligne commencant par 'RESUME:' suivie de 2 phrases maximum, "
        "claires et actionnables, redigees pour une lecture a voix haute."
    )
    body = {
        "model": "hermes-agent",
        "input": prompt,
        "conversation": reglage("hermes.session", "jarvis-delegation"),
    }
    reponse = requests.post(
        f"{base}/v1/responses", json=body,
        headers={"Authorization": f"Bearer {cle}"},
        timeout=int(reglage("hermes.timeout", 900)),
    )
    reponse.raise_for_status()
    data = reponse.json()
    morceaux = []
    for item in data.get("output", []):
        if item.get("type") == "message":
            for bloc in item.get("content", []):
                if bloc.get("type") == "output_text" and bloc.get("text"):
                    morceaux.append(bloc["text"])
    return "\n".join(morceaux).strip() or "(reponse vide d'Hermes)"


def _resume_vocal(texte: str) -> str:
    """Extrait la ligne 'RESUME:' (sinon le dernier paragraphe) pour la voix."""
    for ligne in reversed((texte or "").splitlines()):
        l = ligne.strip()
        if l.lower().startswith(("resume:", "resume :", "résumé:", "résumé :")):
            return l.split(":", 1)[1].strip()
    paras = [p.strip() for p in (texte or "").splitlines() if p.strip()]
    return paras[-1] if paras else (texte or "")


def _journaliser(tache: str, resultat: str) -> None:
    """Garde le resultat COMPLET dans logs/hermes/ (la voix ne dit que le resume)."""
    try:
        from datetime import datetime
        dossier = Path(__file__).resolve().parent.parent / "logs" / "hermes"
        dossier.mkdir(parents=True, exist_ok=True)
        horo = datetime.now().strftime("%Y%m%d-%H%M%S")
        (dossier / f"delegation-{horo}.md").write_text(
            f"# Delegation {horo}\n\n## Tache\n{tache}\n\n## Resultat\n{resultat}\n",
            encoding="utf-8")
    except Exception:
        pass


def deleguer_en_fond(tache: str, intro: str = "Hermes a termine. ",
                     nom_thread: str = "deleguer-hermes") -> str:
    """Reutilisable : delegue une tache a Hermes en tache de fond, journalise le
    resultat complet, et annonce a voix haute un resume court (filtre confidentialite).
    Renvoie tout de suite l'accuse pour Jarvis. Utilise par deleguer_a_hermes ET par
    les outils de contenu (generer_idees, generer_script)."""
    def worker():
        global _EN_COURS
        with _LOCK:
            _EN_COURS += 1
        _pousser_hud()                            # HUD : une tache Hermes de plus
        try:
            resultat = _appeler_hermes(tache)
            _journaliser(tache, resultat)
            resume = confidentialite.filtrer(
                _resume_vocal(resultat), max_car=int(reglage("hermes.resume_max", 500)))
            voix.parler(intro + resume)
            try:                                  # retour Hermes aussi a l'ecran (overlay)
                import overlay
                overlay.afficher(resume, type="reponse")
            except Exception:
                pass
        except Exception as e:
            voix.parler("La delegation a Hermes a echoue. "
                        + confidentialite.filtrer(str(e), 120))
        finally:
            with _LOCK:
                _EN_COURS -= 1
            _maj_tokens()                         # conso Hermes mise a jour apres la tache
            _pousser_hud()
    threading.Thread(target=worker, daemon=True, name=nom_thread).start()
    return "Je confie ca a Hermes. Je te previens des que c'est pret."


@outil(
    nom="deleguer_a_hermes",
    description=(
        "Confie une tache de REFLEXION, d'ANALYSE ou de RECHERCHE DE FOND a Hermes "
        "(agent delibératif local). A appeler DE TOI-MEME, sans demander, des que la "
        "demande est une tache de fond : analyse, veille, recherche longue, synthese, "
        "reflexion approfondie — et bien sur si l'utilisateur dit 'delegue a Hermes', "
        "'fais une recherche de fond', 'lance Hermes sur...'. Jarvis annonce « je "
        "confie ca a Hermes » et previent vocalement quand c'est pret. NE PAS utiliser "
        "pour une question simple/reflexe a laquelle tu peux repondre directement."
    ),
    parametres={
        "type": "object",
        "properties": {
            "tache": {
                "type": "string",
                "description": "La tache/question a confier a Hermes, formulee clairement.",
            }
        },
        "required": ["tache"],
    },
)
def deleguer_a_hermes(tache: str) -> str:
    """Envoie la tache a Hermes en tache de fond ; previent a voix haute a la fin."""
    tache = (tache or "").strip()
    if not tache:
        return "Je n'ai pas compris la tache a deleguer."
    return deleguer_en_fond(tache)
