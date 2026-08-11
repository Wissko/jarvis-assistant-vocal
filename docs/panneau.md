# Panneau de configuration web (local)

Un tableau de bord **servi par le serveur web unifié** de Jarvis, mais
**accessible uniquement en local** : un garde rejette toute requête arrivant par
le tunnel ngrok (en-tête `X-Forwarded-For`, ou `Host` ≠ localhost). Le panneau ne
passe donc **jamais** par Internet, même si le même port sert le pont iPhone.

Ouvre-le dans un navigateur **sur la machine de Jarvis** :

```
http://localhost:8790/panneau
```

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

## 2. Page État (le `status-hermes.ps1` en visuel)

La chaîne complète **UP / DOWN** : serveur Jarvis, serveur MCP, tunnel ngrok,
gateway Hermes, Docker, et la **connexion MCP Hermes → Jarvis**. Bouton
**Reconnecter MCP** = le remède du « parking » (`hermes mcp remove/add jarvis`).

> Le tunnel est **lu**, jamais rouvert (sinon ngrok refuse « endpoint already
> online »). Budget par fournisseur + tâches/crons Hermes : viendront avec la N9.

## 3. Page Permissions (niveaux N1/N2/N3 — N8)

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
