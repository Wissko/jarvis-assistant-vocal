"""Abstraction du modele de langage : le reste du code ignore quel provider tourne.

Trois implementations, choisies par config.yaml :
  - ClaudeProvider  : API Anthropic (cloud, defaut).
  - OllamaProvider  : Ollama en local (http://localhost:11434), 100% offline.
  - CodexProvider   : Codex App Server + OAuth ChatGPT, sans cle API.

Les deux exposent la meme methode `repondre(systeme, historique, outils)` et
renvoient un objet a la forme d'une reponse Anthropic (.stop_reason + .content,
chaque bloc ayant .type / .text / .name / .input / .id). Ainsi la boucle de
dialogue de jarvis14 ne change pas selon le provider.

L'historique reste au format "content blocks" d'Anthropic ; OllamaProvider le
traduit vers/depuis le format d'Ollama de facon interne.
"""
import json
import logging

# Magasin de certificats Windows (Malwarebytes intercepte le TLS : sans ca, les
# appels a l'API Anthropic echouent en "certificate verify failed").
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from core.config import reglage

LOG = logging.getLogger("jarvis")


class Bloc:
    """Imite un bloc de contenu Anthropic (text ou tool_use)."""

    def __init__(self, type, text=None, id=None, name=None, input=None):
        self.type = type
        self.text = text
        self.id = id
        self.name = name
        self.input = input


class Reponse:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


# --------------------------------------------------------------- interface

class ProviderLLM:
    nom = "?"

    def disponible(self):
        return True

    def repondre(self, systeme, historique, outils):
        raise NotImplementedError


# --------------------------------------------------------------- Claude (cloud)

class ClaudeProvider(ProviderLLM):
    nom = "Claude"

    def __init__(self, modele=None):
        import anthropic
        cle = reglage("anthropic.cle", "")
        self.modele = modele or reglage("anthropic.modele", "claude-haiku-4-5")
        self.client = anthropic.Anthropic(api_key=cle) if cle else None

    def disponible(self):
        return self.client is not None

    def repondre(self, systeme, historique, outils):
        # La reponse native Anthropic a deja la bonne forme (.stop_reason/.content).
        rep = self.client.messages.create(
            model=self.modele,
            max_tokens=1024,
            system=[{"type": "text", "text": systeme,
                     "cache_control": {"type": "ephemeral"}}],
            messages=historique,
            tools=outils,
        )
        # Comptabilite (N9) : tokens + cout estime, par jour, cote Jarvis.
        try:
            u = getattr(rep, "usage", None)
            if u is not None:
                from core import budget
                budget.enregistrer(
                    "Claude (Jarvis)", self.modele,
                    getattr(u, "input_tokens", 0) or 0,
                    getattr(u, "output_tokens", 0) or 0,
                    cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
                    cache_creation=getattr(u, "cache_creation_input_tokens", 0) or 0)
        except Exception:
            pass
        return rep


# --------------------------------------------------------------- Codex (OAuth ChatGPT)

class CodexProvider(ProviderLLM):
    nom = "Codex"

    def __init__(self, modele=None):
        from core.codex_app_server import CodexAppServer
        self.modele = modele or reglage("codex.modele", "auto")
        self.effort = reglage("codex.reasoning_effort", "medium")
        self.timeout = int(reglage("codex.timeout", 180) or 180)
        self.client = CodexAppServer(
            reglage("codex.executable", "codex"),
            reglage("codex.login_timeout", 180),
            reglage("codex.home", "logs/codex-home"))
        self._compte_verifie = False

    def disponible(self):
        if not self.client.disponible():
            return False
        if not self._compte_verifie:
            try:
                self._compte_verifie = self.client.compte(connecter=True) is not None
            except Exception as e:
                LOG.warning("codex: compte indisponible (%s)", e)
                return False
        return self._compte_verifie

    @staticmethod
    def _historique(historique):
        lignes = []
        for message in historique:
            role = message.get("role", "user")
            contenu = message.get("content", "")
            if isinstance(contenu, str):
                lignes.append(f"{role}: {contenu}")
                continue
            morceaux = []
            for bloc in contenu or []:
                if isinstance(bloc, dict):
                    if bloc.get("type") == "tool_result":
                        morceaux.append("RESULTAT_OUTIL " + json.dumps({
                            "id": bloc.get("tool_use_id"),
                            "contenu": bloc.get("content")}, ensure_ascii=False, default=str))
                    elif bloc.get("type") == "text":
                        morceaux.append(str(bloc.get("text", "")))
                elif getattr(bloc, "type", None) == "text":
                    morceaux.append(bloc.text or "")
                elif getattr(bloc, "type", None) == "tool_use":
                    morceaux.append("APPEL_OUTIL " + json.dumps({
                        "id": bloc.id, "nom": bloc.name, "arguments": bloc.input or {}},
                        ensure_ascii=False))
            lignes.append(f"{role}: " + "\n".join(morceaux))
        return "Conversation Jarvis a poursuivre :\n" + "\n\n".join(lignes)

    @staticmethod
    def _outils(outils):
        return [{
            "type": "function",
            "name": o["name"],
            "description": o.get("description", ""),
            "inputSchema": o.get("input_schema", {"type": "object", "properties": {}}),
        } for o in outils]

    def repondre(self, systeme, historique, outils):
        textes, appels = self.client.tour(
            systeme, self._historique(historique), self._outils(outils),
            modele=self.modele, effort=self.effort, timeout=self.timeout)
        blocs = [Bloc("text", text=t) for t in textes if t.strip()]
        blocs.extend(Bloc("tool_use", id=a["id"], name=a["name"], input=a["input"])
                     for a in appels)
        return Reponse("tool_use" if appels else "end", blocs)


# --------------------------------------------------------------- Ollama (local)

class OllamaProvider(ProviderLLM):
    nom = "Ollama"

    def __init__(self):
        self.hote = reglage("ollama.hote", "http://localhost:11434").rstrip("/")
        self.modele = reglage("ollama.modele", "qwen3.5:4b")

    def disponible(self):
        try:
            import requests
            requests.get(f"{self.hote}/api/version", timeout=3)
            return True
        except Exception:
            return False

    # -- traduction historique Anthropic -> messages Ollama --
    def _traduire(self, systeme, historique):
        messages = [{"role": "system", "content": systeme}]
        for m in historique:
            role, contenu = m.get("role"), m.get("content")
            if role == "user":
                if isinstance(contenu, str):
                    messages.append({"role": "user", "content": contenu})
                else:
                    for item in contenu or []:
                        if not isinstance(item, dict):
                            continue
                        if item.get("type") == "tool_result":
                            c = item.get("content")
                            if isinstance(c, list):   # bloc image
                                c = "[image capturee — la vision n'est pas disponible en mode local]"
                            messages.append({"role": "tool", "content": str(c)})
                        elif item.get("type") == "image":
                            messages.append({"role": "user",
                                             "content": "[image — vision indisponible en local]"})
            else:  # assistant
                if isinstance(contenu, str):
                    messages.append({"role": "assistant", "content": contenu})
                else:
                    texte = " ".join(b.text for b in (contenu or [])
                                     if getattr(b, "type", None) == "text" and b.text)
                    appels = [b for b in (contenu or []) if getattr(b, "type", None) == "tool_use"]
                    msg = {"role": "assistant", "content": texte}
                    if appels:
                        msg["tool_calls"] = [
                            {"function": {"name": b.name, "arguments": b.input or {}}}
                            for b in appels]
                    messages.append(msg)
        return messages

    def _outils(self, outils):
        return [{"type": "function", "function": {
            "name": o["name"], "description": o["description"],
            "parameters": o.get("input_schema", {"type": "object", "properties": {}})}}
            for o in outils]

    def _chat(self, messages, tools, nudge=None):
        import requests
        if nudge:
            messages = messages + [{"role": "user", "content": nudge}]
        # think=false : desactive le "raisonnement" natif (qwen3.5, etc.). Sinon le
        # modele est tres lent et rend parfois ses appels d'outils en texte au lieu
        # de les executer. Un modele sans thinking ignore ce parametre.
        r = requests.post(f"{self.hote}/api/chat", timeout=120, json={
            "model": self.modele, "messages": messages, "tools": tools,
            "stream": False, "think": bool(reglage("ollama.think", False)),
            "options": {"temperature": 0.3}})
        r.raise_for_status()
        return r.json()

    def _parser(self, rep):
        msg = rep.get("message", {}) or {}
        blocs = []
        texte = (msg.get("content") or "").strip()
        if texte:
            blocs.append(Bloc("text", text=texte))
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function", {}) or {}
            args = fn.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)   # peut lever -> gere par le retry
            blocs.append(Bloc("tool_use", id=f"call_{i}", name=fn.get("name"), input=args or {}))
        stop = "tool_use" if any(b.type == "tool_use" for b in blocs) else "end"
        return Reponse(stop, blocs)

    def repondre(self, systeme, historique, outils):
        messages = self._traduire(systeme, historique)
        tools = self._outils(outils)
        try:
            return self._parser(self._chat(messages, tools))
        except Exception as e:
            LOG.warning("ollama: 1er essai en echec (%s), retry plus directif", e)
            # Retry unique, avec une consigne plus stricte sur l'appel d'outil.
            nudge = ("Rappel : pour agir, appelle l'outil approprie via un tool call "
                     "avec des arguments JSON valides ; sinon reponds simplement en texte.")
            try:
                return self._parser(self._chat(messages, tools, nudge=nudge))
            except Exception:
                LOG.exception("ollama: echec apres retry")
                return Reponse("end", [Bloc("text", text=(
                    "Desole, le modele local n'a pas reussi a traiter la demande "
                    "correctement. Reessaie en reformulant, ou repasse en mode cloud."))])


# --------------------------------------------------------------- fabrique

_LLM = None


def llm():
    """Provider LLM courant selon le mode (local | hybride | qualite).

    - local   : Ollama.
    - hybride : Codex OAuth (ou Claude si codex.actif=false).
    - qualite : Codex OAuth (ou Claude si codex.actif=false)."""
    global _LLM
    if _LLM is None:
        from core.routage import mode_actuel
        m = mode_actuel()
        if m == "local":
            _LLM = OllamaProvider()
        elif reglage("codex.actif", True):
            _LLM = CodexProvider(reglage("codex.modele", "auto"))
        elif m == "qualite":
            _LLM = ClaudeProvider(reglage("anthropic.modele_qualite",
                                          "claude-sonnet-4-5"))
        else:                                    # hybride (defaut)
            _LLM = ClaudeProvider(reglage("anthropic.modele", "claude-haiku-4-5"))
        LOG.info("provider LLM : %s (mode %s, modele %s)",
                 _LLM.nom, m, getattr(_LLM, "modele", "-"))
    return _LLM


def reinitialiser():
    """Force la reconstruction du provider au prochain llm() (apres un switch de mode)."""
    global _LLM
    _LLM = None
