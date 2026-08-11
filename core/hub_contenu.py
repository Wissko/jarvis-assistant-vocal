"""Hub de contenu : pipeline d'ingestion d'une inspiration (Insta/TikTok) au Vault.

Le CHAINON MANQUANT, c'est l'INDEXEUR (le "greffier") : ingest.py depose une fiche
brute dans Vault/raw/, puis ce module la lit, demande a Claude un RESUME + des
THEMES + un enrichissement (tags/format/pourquoi), APPEND l'entree a index.md
(dedup par shortcode), enrichit le front-matter de la fiche, met a jour
progression.txt, puis relance graphe.py + build_vault.py, et (option) miroir Drive.

Regles (fiches A/B + 4bis) :
  - Jarvis est le SEUL greffier de index.md : append-only, dedup par <shortcode>.
  - ingest.py n'est PAS modifie ; l'enrichissement du front-matter se fait ICI,
    sur la fiche que le pipeline vient de creer (les anciennes fiches sont
    laissees telles quelles ; parsing tolerant).
  - build_vault.py / graphe.py se lancent avec cwd = racine du Vault.
  - Whisper tourne en CPU (GPU casse) ; ingest.py force deja device="cpu".

Chemins dans config.yaml -> section `integrations:` (vault, scripts, cookies) et
`hub:` (modele d'indexation, miroir Drive).
"""
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from core.config import reglage

LOG = logging.getLogger("jarvis")

_URL_INSTA_TIKTOK = re.compile(
    r"(instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+))"
    r"|(tiktok\.com/[^/]+/video/(\d+))", re.I)


# ------------------------------------------------------------------ chemins

def _vault() -> Path:
    return Path(reglage("integrations.vault", "") or str(Path.home() / "Vault"))


def _cookies() -> str:
    return reglage("integrations.cookies", "firefox")


# ------------------------------------------------------------- shortcode / dedup

def _shortcode_url(url: str) -> str:
    """Shortcode Insta (ou id TikTok) depuis une URL."""
    m = _URL_INSTA_TIKTOK.search(url or "")
    if not m:
        return ""
    return m.group(2) or m.group(4) or ""


def _shortcode_fiche(nom: str) -> str:
    """insta_ABC123.md -> ABC123 ; tiktok_12345.md -> 12345."""
    base = Path(nom).stem
    for prefixe in ("insta_", "tiktok_"):
        if base.startswith(prefixe):
            return base[len(prefixe):]
    return base


def _shortcodes_indexes(index_texte: str) -> set:
    """Tous les <shortcode> deja presents dans index.md (dedup)."""
    codes = set()
    for m in _URL_INSTA_TIKTOK.finditer(index_texte or ""):
        code = m.group(2) or m.group(4)
        if code:
            codes.add(code)
    return codes


# ------------------------------------------------------------- lecture de fiche

def _lire_fiche(chemin: Path) -> dict:
    """Parse tolerant : front-matter (---) + sections ## . Robuste aux vieilles fiches."""
    texte = chemin.read_text(encoding="utf-8", errors="ignore")
    meta, corps = {}, texte
    if texte.startswith("---"):
        fin = texte.find("\n---", 3)
        if fin != -1:
            entete = texte[3:fin].strip()
            corps = texte[fin + 4:]
            for ligne in entete.splitlines():
                if ":" in ligne:
                    cle, val = ligne.split(":", 1)
                    meta[cle.strip()] = val.strip()

    def section(nom):
        m = re.search(rf"##\s*{re.escape(nom)}\s*\n(.*?)(?=\n##\s|\Z)", corps, re.S)
        return (m.group(1).strip() if m else "")

    titre = ""
    mt = re.search(r"^#\s+(.+)$", corps, re.M)
    if mt:
        titre = mt.group(1).strip()
    return {
        "meta": meta,
        "titre": titre,
        "description": section("Description"),
        "transcription": section("Transcription audio"),
        "texte": texte,
    }


# ------------------------------------------------------------- indexeur (LLM)

def _themes_existants(index_texte: str, limite: int = 60) -> list:
    """Vocabulaire de themes deja utilise (pour eviter la proliferation)."""
    cpt = {}
    for m in re.finditer(r"^- th[eè]mes\s*:\s*(.+)$", index_texte, re.M | re.I):
        for t in m.group(1).split(","):
            t = t.strip()
            if t:
                cpt[t] = cpt.get(t, 0) + 1
    return [t for t, _ in sorted(cpt.items(), key=lambda kv: -kv[1])[:limite]]


def _analyser_llm(fiche: dict, commentaire: str, themes_existants: list) -> dict:
    """Demande a Claude : titre court, themes, resume concret, tags, format.

    Renvoie un dict ; leve en cas d'echec dur (l'appelant gere).
    """
    import anthropic
    cle = reglage("anthropic.cle", "")
    if not cle:
        raise RuntimeError("cle Anthropic absente (anthropic.cle)")
    modele = (reglage("hub.modele", "") or reglage("anthropic.modele", "")
              or "claude-haiku-4-5")
    client = anthropic.Anthropic(api_key=cle)

    desc = (fiche.get("description") or "").strip()
    trans = (fiche.get("transcription") or "").strip()
    auteur = fiche["meta"].get("auteur", "inconnu")
    systeme = (
        "Tu indexes une video sauvegardee (Instagram/TikTok) pour un createur de "
        "contenu. A partir de la description et de la transcription, tu produis une "
        "fiche d'index CONCRETE et factuelle, en francais. N'invente rien : si une "
        "info manque, ne la mets pas. Reponds UNIQUEMENT par un objet JSON."
    )
    vocab = ", ".join(themes_existants) or "(aucun)"
    prompt = f"""Auteur : {auteur}

DESCRIPTION :
{desc[:2000] or "(vide)"}

TRANSCRIPTION :
{trans[:4000] or "(vide)"}

Themes deja utilises dans l'index (REUTILISE-les quand c'est pertinent, sinon cree
un theme court et generique) : {vocab}

Renvoie ce JSON exact :
{{
  "titre": "titre court et parlant (max 90 caracteres), sans guillemets superflus",
  "themes": ["1 a 3 themes"],
  "contenu": "resume concret en 1 a 3 phrases : de quoi ca parle, l'info utile, pas de blabla",
  "tags": ["3 a 6 mots-cles minuscules"],
  "format": "un seul parmi: talking head, tuto, storytelling, trend, interview, sketch, vlog, demo produit, motivation, autre"
}}"""
    rep = client.messages.create(
        model=modele, max_tokens=700,
        system=[{"type": "text", "text": systeme}],
        messages=[{"role": "user", "content": prompt}],
    )
    texte = "".join(b.text for b in rep.content if getattr(b, "type", None) == "text")
    m = re.search(r"\{.*\}", texte, re.S)
    if not m:
        raise RuntimeError("l'indexeur n'a pas renvoye de JSON")
    data = json.loads(m.group(0))
    # garde-fous
    data.setdefault("titre", fiche.get("titre") or "Sans titre")
    data["titre"] = str(data["titre"]).strip()[:90]
    data["themes"] = [str(t).strip() for t in (data.get("themes") or []) if str(t).strip()][:3] or ["Autre"]
    data["tags"] = [str(t).strip().lower() for t in (data.get("tags") or []) if str(t).strip()][:6]
    data["format"] = str(data.get("format") or "autre").strip().lower()
    data["contenu"] = str(data.get("contenu") or "").strip()
    return data


# ------------------------------------------------------- ecriture index + fiche

def _entree_index(url: str, auteur: str, analyse: dict) -> str:
    themes = ", ".join(analyse["themes"])
    return (f"\n### {analyse['titre']}\n"
            f"- lien : {url}\n"
            f"- auteur : {auteur}\n"
            f"- thèmes : {themes}\n"
            f"- contenu : {analyse['contenu']}\n")


def _dureh(duree_s) -> str:
    try:
        s = int(float(duree_s))
        return f"{s // 60}:{s % 60:02d}"
    except (TypeError, ValueError):
        return ""


def _enrichir_frontmatter(chemin: Path, analyse: dict, commentaire: str) -> None:
    """Ajoute tags/format/date_ajout/duree/pourquoi au front-matter de la fiche
    (uniquement les cles absentes ; le reste est preserve). Nouvelle fiche du
    pipeline : on n'ecrit jamais dans les anciennes."""
    texte = chemin.read_text(encoding="utf-8", errors="ignore")
    if not texte.startswith("---"):
        return
    fin = texte.find("\n---", 3)
    if fin == -1:
        return
    entete = texte[3:fin]
    reste = texte[fin:]  # a partir du \n---
    existantes = {l.split(":", 1)[0].strip() for l in entete.splitlines() if ":" in l}
    meta = {l.split(":", 1)[0].strip(): l.split(":", 1)[1].strip()
            for l in entete.splitlines() if ":" in l}
    ajouts = []
    if "tags" not in existantes:
        ajouts.append("tags: [" + ", ".join(analyse.get("tags", [])) + "]")
    if "format" not in existantes:
        ajouts.append(f"format: {analyse.get('format', 'autre')}")
    if "themes" not in existantes:
        ajouts.append("themes: [" + ", ".join(analyse.get("themes", [])) + "]")
    if "date_ajout" not in existantes:
        ajouts.append(f"date_ajout: {datetime.now():%Y-%m-%d}")
    if "duree" not in existantes:
        d = _dureh(meta.get("duree_s"))
        if d:
            ajouts.append(f"duree: {d}")
    if "pourquoi" not in existantes and commentaire:
        propre = commentaire.replace("\n", " ").strip().replace('"', "'")
        ajouts.append(f'pourquoi: "{propre}"')
    if not ajouts:
        return
    nouvelle_entete = entete.rstrip() + "\n" + "\n".join(ajouts) + "\n"
    chemin.write_text("---" + nouvelle_entete + reste, encoding="utf-8")


def _maj_progression(vault: Path, fiche_nom: str, total: int) -> None:
    (vault / "progression.txt").write_text(
        f"Derniere fiche indexee : {fiche_nom}\n"
        f"Fiches indexees : {total}\n"
        f"Date : {datetime.now():%Y-%m-%d %H:%M}\n"
        f"Greffier : pipeline Jarvis (append-only, dedup shortcode)\n",
        encoding="utf-8")


# ------------------------------------------------------------- outils externes

def _lancer(cmd, vault: Path, timeout=180) -> tuple:
    env = dict(os.environ, WHISPER_DEVICE="cpu")
    r = subprocess.run(cmd, cwd=str(vault), capture_output=True, text=True,
                       timeout=timeout, env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _rendre_vault(vault: Path) -> None:
    """graphe.py (themes -> fiches + themes/) puis build_vault.py (vault.html)."""
    code, sortie = _lancer([sys.executable, "graphe.py"], vault, timeout=120)
    if code != 0:
        LOG.warning("graphe.py code %s : %s", code, sortie[-300:])
    code, sortie = _lancer([sys.executable, "build_vault.py"], vault, timeout=120)
    if code != 0:
        LOG.warning("build_vault.py code %s : %s", code, sortie[-300:])


def _miroir(vault: Path) -> str:
    """Miroir index.md + vault.html vers un dossier de consultation a distance
    (par defaut un dossier iCloudDrive synchronise, meme mecanisme que l'inbox).
    Configurable via hub.miroir_dossier ; no-op si vide (confort, pas coeur)."""
    dossier = reglage("hub.miroir_dossier", "")
    if not dossier:
        return "miroir non configure (ignore)"
    import shutil
    dst = Path(dossier)
    try:
        dst.mkdir(parents=True, exist_ok=True)
        for f in ("index.md", "vault.html"):
            src = vault / f
            if src.exists():
                shutil.copy2(src, dst / f)
        return f"miroir OK -> {dossier}"
    except Exception as e:
        LOG.warning("miroir echec : %s", e)
        return f"miroir echec : {e}"


# ------------------------------------------------------------- ingestion brute

def _ingerer_brut(url: str, vault: Path) -> Path:
    """Lance ingest.py sur une URL unique ; renvoie le chemin de la fiche raw creee.
    Leve RuntimeError clair si video privee/indisponible (au lieu d'echec muet)."""
    raw = vault / "raw"
    shortcode = _shortcode_url(url)
    attendu = None
    if shortcode:
        prefixe = "tiktok_" if "tiktok" in url.lower() else "insta_"
        attendu = raw / f"{prefixe}{shortcode}.md"
        if attendu.exists():
            return attendu  # deja ingere

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as tmp:
        tmp.write(url + "\n")
        fichier_liens = tmp.name
    try:
        code, sortie = _lancer(
            [sys.executable, "ingest.py", fichier_liens,
             "--vault", str(vault), "--cookies", _cookies(), "--limite", "1"],
            vault, timeout=int(reglage("hub.timeout_ingest", 600)))
    finally:
        try:
            os.unlink(fichier_liens)
        except OSError:
            pass

    # fiche creee ?
    if attendu and attendu.exists():
        return attendu
    # sinon : diagnostic via journal.json (statut echec + erreur)
    try:
        journal = json.loads((vault / "journal.json").read_text(encoding="utf-8"))
        entree = journal.get(url) or {}
        if entree.get("statut") == "echec":
            raise RuntimeError(
                "video privee ou indisponible : "
                + (entree.get("erreur") or "telechargement impossible"))
    except (OSError, json.JSONDecodeError):
        pass
    raise RuntimeError("aucune fiche produite (video privee/indisponible ou lien invalide). "
                       + sortie[-200:].strip())


# ------------------------------------------------------------- API publique

def indexer_fiche(chemin: Path, commentaire: str = "") -> dict:
    """Indexe UNE fiche raw deja presente (greffier) : append index.md (dedup),
    enrichit le front-matter, maj progression, rerend le Vault. Idempotent."""
    vault = _vault()
    chemin = Path(chemin)
    shortcode = _shortcode_fiche(chemin.name)
    index = vault / "index.md"
    index_texte = index.read_text(encoding="utf-8") if index.exists() else ""
    if shortcode and shortcode in _shortcodes_indexes(index_texte):
        return {"ok": True, "deja_indexe": True, "shortcode": shortcode,
                "titre": None, "message": "deja dans l'index"}

    fiche = _lire_fiche(chemin)
    url = fiche["meta"].get("source", "")
    auteur = fiche["meta"].get("auteur", "inconnu")
    analyse = _analyser_llm(fiche, commentaire, _themes_existants(index_texte))

    # APPEND (append-only)
    with index.open("a", encoding="utf-8") as f:
        f.write(_entree_index(url, auteur, analyse))
    _enrichir_frontmatter(chemin, analyse, commentaire)
    total = len(_shortcodes_indexes(index.read_text(encoding="utf-8")))
    _maj_progression(vault, chemin.name, total)
    _rendre_vault(vault)
    miroir = _miroir(vault)
    return {"ok": True, "shortcode": shortcode, "titre": analyse["titre"],
            "auteur": auteur, "themes": analyse["themes"], "miroir": miroir,
            "message": f"Inspiration ajoutee au vault : {analyse['titre']} — {auteur}"}


def ingerer_inspiration(url: str, commentaire: str = "") -> dict:
    """Pipeline complet depuis une URL : ingest.py (brut) -> indexeur -> rendu.
    Renvoie un dict avec ok/titre/auteur/message (pour la notif vocale de Jarvis)."""
    vault = _vault()
    if not vault.exists():
        return {"ok": False, "message": f"Vault introuvable : {vault}"}
    try:
        fiche = _ingerer_brut(url, vault)
    except Exception as e:
        return {"ok": False, "message": f"Echec de l'ingestion : {e}"}
    try:
        res = indexer_fiche(fiche, commentaire)
        res["url"] = url
        return res
    except Exception as e:
        LOG.exception("indexation")
        return {"ok": False, "message": f"Fiche telechargee mais indexation echouee : {e}"}


def indexer_manquantes(limite: int = 0) -> dict:
    """Indexe toutes les fiches de raw/ absentes de l'index (dedup shortcode).
    Utile apres un depot en lot dans raw/ (flux iCloud) ou pour rattraper."""
    vault = _vault()
    raw = vault / "raw"
    index = vault / "index.md"
    deja = _shortcodes_indexes(index.read_text(encoding="utf-8") if index.exists() else "")
    a_faire = [p for p in sorted(raw.glob("*.md"))
               if _shortcode_fiche(p.name) not in deja]
    if limite:
        a_faire = a_faire[:limite]
    faits = []
    for p in a_faire:
        try:
            r = indexer_fiche(p)
            if not r.get("deja_indexe"):
                faits.append(r.get("titre") or p.name)
        except Exception as e:
            LOG.warning("indexation %s : %s", p.name, e)
    return {"ok": True, "indexes": len(faits), "titres": faits,
            "restant": len(a_faire) - len(faits)}
