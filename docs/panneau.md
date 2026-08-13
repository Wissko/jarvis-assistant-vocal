# Panneau de configuration web (local)

Un tableau de bord **servi par le serveur web unifié** de Jarvis, mais
**accessible uniquement en local** : un garde rejette toute requête arrivant par
le tunnel ngrok (en-tête `X-Forwarded-For`, ou `Host` ≠ localhost). Le panneau ne
passe donc **jamais** par Internet, même si le même port sert le pont iPhone.

Ouvre-le dans un navigateur **sur la machine de Jarvis** :

```
http://localhost:8790/panneau
```

**À la voix** : « **ouvre le tableau de configuration** » (ou « tableau de bord »,
« ouvre le panneau ») → l'outil `ouvrir_panneau` (N1, local, non exposé au MCP)
lance le navigateur sur cette page. Si le serveur n'est pas démarré, Jarvis le dit.

**Doctrine** : c'est du **Jarvis pur** (config locale). Il *affiche* l'état
d'Hermes mais ne lui donne **aucun droit nouveau**. Il n'écrit que ce qui est sans
danger (choix de modèle, modèle d'Hermes) — **jamais une règle de sécurité**.

## 1. Page Modèles (la pièce maîtresse)

- **Matériel** : GPU, VRAM totale et *exploitable* (total − marge pour l'OS +
  Whisper CPU), via la même logique que `scripts/doctor.py` (pynvml).
- **Modèles LLM locaux (Ollama)** : un **catalogue recommandé** avec des badges
  par modèle — *tient en VRAM* (mémoire requise vs exploitable), *tool calling*,
  *français*, *licence*, *taille* — plus la liste de tes modèles déjà installés.
  Boutons : **Installer** (`ollama pull`, avec barre de progression), **Tester**
  (mini-benchmark : latence + un appel d'outil factice + une phrase en français),
  **Supprimer**, **Activer**.
- **Modèles Whisper** (tiny → large-v3-turbo) : reco + badge *français fiable* ;
  installer / activer / supprimer. (Whisper tourne en **CPU** chez toi.)
- **Modèle actif par backend** : local (Ollama), cloud (Claude), Whisper et
  **Hermes** — affiché et changeable en un clic (écrit dans `config.yaml`, et pour
  Hermes via `hermes config set model.default`). **Redémarre** le composant après.

## 2. Page Réglages (voix, audio, mot d'activation)

Les réglages du quotidien, écrits dans `config.yaml` (**redémarre Jarvis** pour les
appliquer). Écriture **whitelistée** : seules ces clés sont modifiables depuis le
panneau — jamais une clé/secret (`_CLES_REGLABLES` dans `core/panneau.py`).

- **Mode de routage** : `local` (tout sur ta machine, gratuit/privé) vs `cloud`
  (Claude, plus fin, payant) → `mode`. Le *modèle précis* reste dans l'onglet Modèles.
- **Audio** : **micro** (`audio.micro`) et **haut-parleur** (`audio.haut_parleur`,
  « défaut » = sortie Windows) — listés en direct via `sounddevice.query_devices()`.
- **Voix & écoute** : **personnalité** (`assistant.personnalite`) et **durée
  d'écoute enchaînée** (`assistant.duree_suite`, secondes où Jarvis continue
  d'écouter après une réponse sans redire le mot d'activation).
- **Mot d'activation** : la phrase est fixe (« Hey Jarvis », modèle openWakeWord
  embarqué) ; **sensibilité** réglable (`assistant.seuil_reveil` : bas = déclenche
  facilement, haut = strict).

## 3. Page État (le `status-hermes.ps1` en visuel)

La chaîne complète **UP / DOWN** : serveur Jarvis, serveur MCP, tunnel ngrok,
gateway Hermes, Docker, et la **connexion MCP Hermes → Jarvis**. Bouton
**Reconnecter MCP** = le remède du « parking » (`hermes mcp remove/add jarvis`).

> Le tunnel est **lu**, jamais rouvert (sinon ngrok refuse « endpoint already
> online »).

### Budget par fournisseur (N9)

- **Jarvis (mesuré)** : chaque appel Claude est instrumenté (`core/budget.py`) →
  tokens (in/out, cache compris) + **coût estimé** via la table de prix
  `budget.prix` (config). Résumé **du jour** et **du mois**, persistant dans
  `budget.json` (non versionné). Redémarre Jarvis pour activer le comptage.
- **Twilio** : le compteur mensuel existant (`logs/calls/compteur.json`).
- **Hermes** : tokens (jour / 30 j) lus via `hermes insights` — Hermes tient sa
  propre comptabilité, Jarvis ne la double pas.

### Activité Hermes (N9)

Crons planifiés (nom, planning, prochaine exécution), derniers runs de cron, et
tâches kanban en cours — via le CLI `hermes` (`cron list` / `cron runs` /
`kanban list`). *(Les commandes sont lancées en UTF-8 : la sortie d'Hermes
contient cadres et emoji.)*

## 4. Page Permissions (niveaux N1/N2/N3 — N8)

Une seule vue = tout le **périmètre de sécurité**, avec le **niveau de permission**
de chaque outil :

| Niveau | Sens | Confirmation | « toujours autoriser » | À distance (iPhone) |
|---|---|---|---|---|
| **N1** sûr | domotique, PC, lectures | non | — | **oui** |
| **N2** sensible | actions réversibles | oui | **mémorisable** (révocable ici) | non |
| **N3** critique 🔒 | mail, appels, réservations, suppressions | **toujours** | **jamais** | jamais |

- **Mémoriser un N2** : à la voix, réponds **« oui, toujours »** à la demande de
  confirmation → l'outil passe en « toujours autorisé » **en local** (stocké dans
  `config.yaml → securite.toujours`). La page l'affiche avec un bouton **Révoquer**.
- **N3** : confirmation à chaque fois, « toujours » refusé, jamais à distance —
  **verrouillé dans le code** (`core/registre.py → _N3`).
- Le **« toujours autoriser » n'ouvre RIEN à distance** : le pont iPhone teste
  `confirmation` en direct, il ne consulte jamais le store.

La page montre aussi l'**accès fichiers d'Hermes** (montages Docker : `/vault` ro,
`/scripts` ro, `/scripts/drafts` rw).

## Sécurité

- **Local only** : garde sur chaque route (`X-Forwarded-For` / `Host`).
- **Écriture limitée** au sans-danger : sélection de modèle, **révocation d'une
  autorisation « toujours »**, reconnexion MCP. Jamais les règles N3.
- Rien de nouveau n'est accordé à Hermes : le panneau **observe** sa config.
