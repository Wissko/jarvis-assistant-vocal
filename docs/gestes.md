# Contrôle par gestes de la main (webcam)

Piloter Jarvis d'un geste, en **temps réel** et **100 % en local**. Pensé pour être
**fiable** (petit vocabulaire de gestes tenus) et **respectueux de la vie privée**
(aucune image ne quitte jamais la machine, ni même le sous-process de tracking).

> **Doctrine — Jarvis pur (physique, temps réel).** Aucun rôle pour Hermes ici.
> Les gestes ne déclenchent que des actions **N1/N2** ; **jamais** de N3 (pas
> d'extinction, d'appel, de réservation par geste — un faux pincement ne coûte
> qu'une lumière).

## Pourquoi un sous-process séparé (Python 3.11)

MediaPipe n'a **pas de wheel Python 3.13** (Jarvis tourne en 3.13). Le tracking
tourne donc dans un **venv isolé Python 3.11** (`gestes/.venv-tracker`). C'est aussi
la **frontière vie privée** : ce process est le **seul** à voir l'image ; il n'en
sort que des *labels de gestes* (`"poing"`, `"pincement_haut"`…), envoyés à Jarvis
en **loopback** local. Bonus : process séparé = **il ne vole rien à Whisper** (CPU
ordonnancé par l'OS).

```
Webcam USB → [sous-process 3.11 : OpenCV + MediaPipe HandLandmarker + FSM anti-faux-positif]
               └─ POST http://127.0.0.1:8790/api/gestes  {geste: "poing"}   (loopback + token)
Jarvis (3.13) : core/gestes.py → mappe → action N1/N2 → feedback (bip + flash HUD)
```

## Installation

```bash
python scripts/setup_gestes.py
```

Crée le venv 3.11, installe `mediapipe`/`opencv-python`/`requests`, télécharge le
modèle `hand_landmarker.task` (~8 Mo). **Une webcam USB** est requise (pas une caméra
IP : latence rédhibitoire).

Puis, à la voix : **« Jarvis, active les gestes »** / **« coupe les gestes »**, ou
`gestes.actif: true` dans `config.yaml`, ou le **raccourci clavier** (défaut
`Ctrl+Alt+G`).

## Le vocabulaire (v1) et le mapping par défaut

Des gestes **tenus** (pas d'instantané) pour éviter les faux positifs :

| Geste | Action par défaut |
|---|---|
| **Pincement** (pouce-index) + **glisser vertical** | Luminosité de la pièce (± par pas) |
| **Main ouverte** tenue ~1 s | Play / pause musique |
| **Poing** tenu ~1 s | **Couper le TTS** en cours (le « stop » silencieux — pratique en call) |
| **Swipe** gauche / droite | **Contextuel en cascade** (voir ci-dessous) |

Chaque geste reconnu = **feedback discret** (petit bip + flash HUD) pour savoir que
c'est pris. Le mapping est **entièrement éditable** dans `config.yaml → gestes.mapping`.

### Le swipe est contextuel (du plus spécifique au plus général)

Un swipe gauche/droite fait **une chose différente selon ce qui est au premier plan**,
avec un **retour overlay** qui indique le mode :

1. **OBS actif / en live** → scène OBS précédente / suivante — 📺 « Scène OBS suivante ».
2. **Une app vidéo au premier plan** (YouTube dans le navigateur, VLC, lecteur…) →
   **seek −10 s / +10 s** (touches envoyées à l'app qui a le focus) — 🎬 « +10s ».
3. **Sinon** → **bascule de fenêtre** style Alt+Tab (fenêtre précédente / suivante) —
   🪟 « Fenêtre suivante ».

*(Les pistes musicales ne sont plus sur le swipe — la voix s'en charge.)*
**Backlog v2** : swipe à **deux doigts** = déplacer la fenêtre active vers l'autre écran.

## Anti-faux-positifs (le vrai défi)

- **Gestes tenus** : un poing / une main ouverte doit être maintenu `tenue_s` (1 s).
- **Zone morte** sur le glissement du pincement (`deadzone_lum`).
- **Cooldown** entre deux commandes (`cooldown_s`, 1,5 s) — côté tracker *et* côté Jarvis.
- **Swipe par vitesse** (amplitude mini `swipe_seuil` sur une fenêtre courte).
- **Armement optionnel** (`gestes.armement.actif`) : les gestes n'agissent qu'après
  une **main levée 2 s** (« Jarvis regarde »), pendant une fenêtre de quelques secondes.

## Calibration (à l'arrivée de la webcam)

```bash
python scripts/gestes_calibrer.py
```

Affiche la caméra + les landmarks + les métriques en direct. Règle les seuils au
clavier — `+`/`-` (pincement), `t`/`T` (durée de maintien) — `s` **sauvegarde** vers
`gestes/calibration.json` (prioritaire sur `config.yaml`), `q` quitte. **Aucune image
n'est enregistrée** pendant la calibration.

## Caméra : cycle de vie & cohabitation

- **On/off** : à la voix (`controler_gestes`), au raccourci clavier, ou `gestes.actif`.
  À l'arrêt de Jarvis, la webcam est **libérée** (`atexit`).
- **Choix du périphérique** : `gestes.device` (0 = première webcam USB).
- **Statut** : `GET http://127.0.0.1:8790/api/gestes/status` → `{actif}` (repris dans
  `hermes-workspace/status-hermes.ps1` : *Tracker de gestes : UP/DOWN*).
- **Cohabitation stream** : pendant un **direct OBS**, le swipe **change de scène**
  (c'est le mode 1 de la cascade). Si OBS occupe déjà la webcam physique, sélectionne
  une autre `device`, ou utilise la **caméra virtuelle OBS** comme source des gestes.
  *(`gestes.pause_pendant_live` ne s'applique plus au swipe contextuel, seulement à
  l'ancienne action `obs_scene` si tu la remets dans le mapping.)*
- **Indicateur** : la LED de la webcam s'allume quand la caméra est active — jamais
  de capture à ton insu.

## 🔒 Vie privée (une caméra chez soi = sujet sérieux)

- **Traitement 100 % local.** Aucune image n'est **stockée**, **loggée** ni
  **transmise**. Seules des **coordonnées de landmarks** existent en mémoire du
  sous-process, et elles ne sont **même pas écrites dans les logs**.
- Ce qui traverse vers Jarvis : **uniquement un label de geste** (une chaîne).
- La caméra n'est **JAMAIS** exposée en **MCP** ni accessible à **Hermes**
  (`controler_gestes` est `mcp_expose=False`).
- L'endpoint `/api/gestes` est **loopback + token** : un process local malveillant ne
  peut pas injecter de faux gestes sans le jeton (généré à chaque activation, connu du
  seul sous-process lancé par Jarvis).

## 🛡️ Sécurité — N1/N2 uniquement

Un geste ne peut déclencher qu'une action **sûre** (lumières, média, couper le TTS,
scènes OBS). Double garde-fou dans `core/gestes.py` :
1. Seules les actions d'une **liste blanche** (`_ACTIONS_SURES`) sont exécutables.
2. Toute action qui viserait un outil classé **N3** est **refusée** en amont
   (`_verifier_non_n3`). Impossible d'éteindre le PC, d'appeler ou de réserver d'un
   geste — même en modifiant le mapping.

## Configuration (`config.yaml → gestes`)

Voir `config.example.yaml` pour toutes les clés (device, fps, seuils, armement,
mapping, `pause_pendant_live`, `raccourci`). `gestes/calibration.json` (issu de la
calibration) **prime** sur `gestes.seuils`.
