"""Pont iPhone : endpoint HTTP pour envoyer notes et commandes depuis le telephone.

Sert POST /api/inbox (FastAPI). Tu l'exposes via ton domaine ngrok statique et tu
l'appelles depuis l'app Raccourcis d'iOS (voir docs/iphone.md).

  { "type": "note",     "contenu": "...", "categorie": "..."(optionnel) }
  { "type": "commande", "contenu": "eteins les lumieres" }

Authentification : un token secret (config pont_iphone.token) dans l'en-tete
X-Jarvis-Token.

SECURITE (essentiel) : une commande a distance ne peut declencher QUE des outils
surs (domotique/PC exposes via MCP, sans confirmation). Toute action sensible
(mail, reservation, appel, suppression...) est refusee -> "a faire a la voix a la
maison". Ainsi un token vole ne peut qu'allumer/eteindre des lumieres, pas reserver
un resto ni passer un appel.
"""
import logging
import secrets

from core.config import reglage

LOG = logging.getLogger("jarvis")


def _token_ok(fourni):
    attendu = reglage("pont_iphone.token", "")
    return bool(attendu) and secrets.compare_digest(str(fourni or ""), str(attendu))


def traiter_commande(phrase):
    """Execute une commande a distance, mais UNIQUEMENT via les outils surs
    (mcp_expose=True et sans confirmation). Renvoie {ok, reponse, faits}."""
    from core.llm import llm
    from core import registre
    P = llm()
    if not P.disponible():
        return {"ok": False, "reponse": "Le modele de Jarvis n'est pas disponible."}
    systeme = ("Tu es Jarvis, pilote a distance. Execute la commande de l'utilisateur "
               "via les outils. Reponds en UNE phrase tres courte, en francais.")
    messages = [{"role": "user", "content": phrase}]
    faits = []
    for _ in range(4):
        try:
            rep = P.repondre(systeme, messages,
                             registre.schemas_api(local_seulement=(P.nom == "Ollama")))
        except Exception as e:
            LOG.exception("pont: appel modele")
            return {"ok": False, "reponse": f"Erreur du modele ({e})."}
        if getattr(rep, "stop_reason", None) != "tool_use":
            texte = " ".join(b.text for b in rep.content
                             if getattr(b, "type", None) == "text").strip()
            return {"ok": True, "faits": faits,
                    "reponse": texte or ("C'est fait." if faits else "Rien a faire.")}
        messages.append({"role": "assistant", "content": rep.content})
        resultats = []
        for b in rep.content:
            if getattr(b, "type", None) != "tool_use":
                continue
            outil = registre.get(b.name)
            if outil is None:
                res = f"Outil inconnu : {b.name}"
            elif outil.confirmation or not outil.mcp_expose:
                res = "Action sensible : a faire a la voix a la maison (refusee a distance)."
            else:
                try:
                    res = str(outil.fonction(**(b.input or {})))
                    faits.append(b.name)
                except Exception:
                    LOG.exception("pont: outil %s", b.name)
                    res = "Erreur pendant l'action."
            LOG.info("pont commande : %s(%s) -> %s", b.name, b.input, str(res)[:100])
            resultats.append({"type": "tool_result", "tool_use_id": b.id, "content": str(res)})
        messages.append({"role": "user", "content": resultats})
    return {"ok": True, "faits": faits, "reponse": "Commande trop longue a traiter."}


def _inspiration_async(url, commentaire):
    """Pipeline hub de contenu en tache de fond ; notif vocale a la fin."""
    from core import hub_contenu, voix
    try:
        res = hub_contenu.ingerer_inspiration(url, commentaire or "")
        if res.get("ok"):
            voix.parler(res.get("message") or "Inspiration ajoutee au vault.")
        else:
            voix.parler("Je n'ai pas pu ajouter l'inspiration. " + (res.get("message") or ""))
    except Exception:
        LOG.exception("pont: inspiration")
        voix.parler("Erreur en ajoutant l'inspiration au vault.")


def monter_routes(app):
    """Ajoute les routes du pont iPhone (/api/inbox, /api/ping) au serveur unifie."""
    import threading

    from fastapi import Header, HTTPException
    from pydantic import BaseModel
    from tools.notes import ajouter_note

    class Entree(BaseModel):
        type: str
        contenu: str | None = None
        categorie: str | None = None
        url: str | None = None
        commentaire: str | None = None

    @app.post("/api/inbox")
    def inbox(entree: Entree, x_jarvis_token: str = Header(default="")):
        if not _token_ok(x_jarvis_token):
            raise HTTPException(status_code=401, detail="Token invalide.")

        if entree.type == "note":
            contenu = (entree.contenu or "").strip()
            if not contenu:
                raise HTTPException(status_code=400, detail="Contenu vide.")
            cat, _ = ajouter_note(contenu, entree.categorie, source="iPhone")
            return {"ok": True, "action": "note", "categorie": cat,
                    "message": f"Note ajoutee dans « {cat} »."}

        if entree.type == "commande":
            contenu = (entree.contenu or "").strip()
            if not contenu:
                raise HTTPException(status_code=400, detail="Contenu vide.")
            r = traiter_commande(contenu)
            return {"ok": r["ok"], "action": "commande",
                    "message": r["reponse"], "faits": r.get("faits", [])}

        if entree.type == "inspiration":
            # url dans "url" (ou "contenu" en repli), commentaire optionnel.
            url = (entree.url or entree.contenu or "").strip()
            if not url:
                raise HTTPException(status_code=400, detail="url manquante.")
            # Tache de fond (telechargement + transcription + indexation = long) ;
            # Jarvis previent a voix haute quand la fiche est indexee.
            threading.Thread(target=_inspiration_async,
                             args=(url, entree.commentaire), daemon=True,
                             name="inspiration").start()
            return {"ok": True, "action": "inspiration",
                    "message": "Inspiration recue, je l'ajoute au vault et je te previens."}

        raise HTTPException(status_code=400,
                            detail="type inconnu (note, commande ou inspiration).")

    @app.get("/api/ping")
    def ping():
        return {"ok": True, "service": "jarvis"}
