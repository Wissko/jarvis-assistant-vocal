"""Client minimal du Codex App Server (JSON-RPC sur stdio).

Codex choisit les outils, mais leur execution reste volontairement dans Jarvis :
les demandes ``item/tool/call`` sont converties en blocs ``tool_use`` par
``core.llm.CodexProvider``. La couche de permissions N1/N2/N3 reste donc l'unique
endroit qui agit sur Windows et les services connectes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import webbrowser


class CodexErreur(RuntimeError):
    pass


def trouver_executable_codex(executable="codex"):
    """Resout Codex dans le PATH ou dans l'installation de l'app Windows.

    L'application Codex range son CLI dans un sous-dossier versionne. Chercher
    ce dossier a chaque creation du client evite de figer un chemin qui devient
    invalide a la prochaine mise a jour de l'application.
    """
    demande = os.path.expandvars(os.path.expanduser(str(executable or "codex")))
    trouve = shutil.which(demande)
    if trouve:
        return os.path.abspath(trouve)
    if os.path.isfile(demande):
        return os.path.abspath(demande)

    if os.name == "nt" and demande.lower() in {"codex", "codex.exe"}:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            dossier_bin = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
            candidats = [dossier_bin / "codex.exe"]
            candidats.extend(dossier_bin.glob("*/codex.exe"))
            existants = [p for p in candidats if p.is_file()]
            if existants:
                # Une mise a jour peut laisser plusieurs versions sur disque.
                return str(max(existants, key=lambda p: p.stat().st_mtime).resolve())
    return demande


class CodexAppServer:
    def __init__(self, executable="codex", login_timeout=180, codex_home=""):
        self.executable_demande = executable or "codex"
        self.executable = trouver_executable_codex(self.executable_demande)
        self.login_timeout = int(login_timeout or 180)
        self.codex_home = os.path.abspath(codex_home) if codex_home else ""
        self._processus = None
        self._lignes = queue.Queue()
        self._id = 0
        self._verrou = threading.RLock()

    def disponible(self):
        return bool(os.path.isfile(self.executable) or shutil.which(self.executable))

    def demarrer(self):
        if self._processus and self._processus.poll() is None:
            return
        if not self.disponible():
            raise CodexErreur(
                f"Executable Codex introuvable : {self.executable_demande}")
        drapeaux = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        environnement = os.environ.copy()
        if self.codex_home:
            os.makedirs(self.codex_home, exist_ok=True)
            environnement["CODEX_HOME"] = self.codex_home
        self._processus = subprocess.Popen(
            [self.executable, "app-server", "--stdio"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=drapeaux, env=environnement)
        threading.Thread(target=self._lire, daemon=True).start()
        self.requete("initialize", {
            "clientInfo": {"name": "jarvis-vocal", "version": "0.1.0"},
            "capabilities": {"experimentalApi": True},
        }, timeout=15)
        self.notification("initialized", {})

    def fermer(self):
        p, self._processus = self._processus, None
        if p and p.poll() is None:
            p.terminate()

    def _lire(self):
        try:
            for ligne in self._processus.stdout:
                try:
                    self._lignes.put(json.loads(ligne))
                except json.JSONDecodeError:
                    continue
        finally:
            self._lignes.put({"_ferme": True})

    def _envoyer(self, message):
        if not self._processus or self._processus.poll() is not None:
            raise CodexErreur("Codex App Server s'est arrete")
        self._processus.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._processus.stdin.flush()

    def notification(self, methode, params=None):
        self._envoyer({"method": methode, "params": params or {}})

    def repondre_requete(self, identifiant, resultat=None, erreur=None):
        msg = {"id": identifiant}
        msg["error" if erreur else "result"] = erreur if erreur else (resultat or {})
        self._envoyer(msg)

    def requete(self, methode, params=None, timeout=30, gestionnaire=None):
        with self._verrou:
            if (methode != "initialize"
                    and (not self._processus or self._processus.poll() is not None)):
                self.demarrer()
            self._id += 1
            identifiant = self._id
            self._envoyer({"id": identifiant, "method": methode, "params": params or {}})
            limite = time.monotonic() + timeout
            notifications = []
            while time.monotonic() < limite:
                try:
                    msg = self._lignes.get(timeout=min(1, max(0.01, limite-time.monotonic())))
                except queue.Empty:
                    continue
                if msg.get("_ferme"):
                    raise CodexErreur("Codex App Server a ferme sa sortie")
                if msg.get("id") == identifiant and ("result" in msg or "error" in msg):
                    if "error" in msg:
                        raise CodexErreur(str(msg["error"]))
                    return msg.get("result") or {}, notifications
                if "method" in msg:
                    if gestionnaire and gestionnaire(msg):
                        continue
                    notifications.append(msg)
            raise CodexErreur(f"Delai depasse pour {methode}")

    def compte(self, connecter=True):
        """Renvoie le compte Codex ; ouvre l'OAuth ChatGPT au premier usage."""
        self.demarrer()
        rep, _ = self.requete("account/read", {"refreshToken": True}, timeout=30)
        compte = rep.get("account")
        if compte or not connecter:
            return compte
        login, _ = self.requete("account/login/start", {"type": "chatgpt"}, timeout=30)
        url = login.get("authUrl") or login.get("auth_url")
        login_id = login.get("loginId") or login.get("login_id")
        if url:
            webbrowser.open(url)
        limite = time.monotonic() + self.login_timeout
        while time.monotonic() < limite:
            try:
                msg = self._lignes.get(timeout=1)
            except queue.Empty:
                continue
            if msg.get("method") == "account/login/completed":
                params = msg.get("params") or {}
                if not login_id or params.get("loginId") in (None, login_id):
                    rep, _ = self.requete("account/read", {}, timeout=30)
                    return rep.get("account")
        raise CodexErreur("Connexion ChatGPT non terminee dans le delai imparti")

    def tour(self, instructions, entree, outils, modele=None, effort="medium", timeout=180):
        """Execute un tour et renvoie (textes, appels_outils)."""
        self.demarrer()
        params = {
            "baseInstructions": instructions,
            "developerInstructions": (
                "Tu es le cerveau de Jarvis. N'execute jamais une action toi-meme. "
                "Utilise uniquement les outils dynamiques fournis. Quand un outil est "
                "demande, Jarvis l'executera apres ce tour avec ses propres permissions."),
            "dynamicTools": outils,
            "sandbox": "read-only",
            "approvalPolicy": "never",
            "ephemeral": True,
        }
        if modele and modele != "auto":
            params["model"] = modele
        demarrage, _ = self.requete("thread/start", params, timeout=30)
        fil = demarrage.get("thread") or {}
        thread_id = fil.get("id") or demarrage.get("threadId")
        if not thread_id:
            raise CodexErreur("thread/start n'a pas renvoye d'identifiant")

        appels, textes = [], []

        def gerer(msg):
            methode, p = msg.get("method"), msg.get("params") or {}
            if methode == "item/tool/call" and "id" in msg:
                appels.append({
                    "id": p.get("callId"), "name": p.get("tool"),
                    "input": p.get("arguments") or {},
                })
                self.repondre_requete(msg["id"], {
                    "success": True,
                    "contentItems": [{"type": "inputText", "text":
                        "Appel transmis a Jarvis pour controle des permissions et execution."}],
                })
                return True
            if methode == "item/completed":
                item = p.get("item") or {}
                if item.get("type") == "agentMessage" and item.get("text"):
                    textes.append(item["text"])
            return False

        tour_params = {
            "threadId": thread_id,
            "input": [{"type": "text", "text": entree}],
            "effort": effort or "medium",
        }
        rep, notifications = self.requete("turn/start", tour_params,
                                           timeout=timeout, gestionnaire=gerer)
        # turn/start confirme seulement le demarrage. Attendre turn/completed.
        turn_id = (rep.get("turn") or {}).get("id")
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            try:
                msg = self._lignes.get(timeout=1)
            except queue.Empty:
                continue
            if gerer(msg):
                continue
            if msg.get("method") == "turn/completed":
                p = msg.get("params") or {}
                fini = p.get("turn") or {}
                if not turn_id or fini.get("id") == turn_id:
                    if fini.get("status") == "failed":
                        raise CodexErreur(str(fini.get("error") or "tour Codex en echec"))
                    return textes, appels
        raise CodexErreur("Delai depasse pendant la reponse Codex")
