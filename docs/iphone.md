# Pont iPhone (app Raccourcis)

Envoie tes **notes/idées** et des **commandes** à Jarvis depuis ton iPhone, où que tu
sois, via l'app **Raccourcis** d'iOS. Idéal pour capter une idée de contenu en
déplacement, ou piloter la maison à distance (« Dis Siri, Dis à Jarvis, mode film »).

## 1. Côté Jarvis (une fois)

1. Génère un **token secret** (une longue chaîne aléatoire). Par exemple :
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(24))"
   ```
2. Dans `config.yaml` :
   ```yaml
   pont_iphone:
     actif: true
     token: "colle-ton-token-ici"
     port: 8790
   ```
3. **Expose le port via ton domaine ngrok statique** (le serveur écoute en local sur
   8790) :
   ```bash
   ngrok http --domain=ton-domaine-statique.ngrok.app 8790
   ```
   L'URL de base de tes raccourcis sera alors `https://ton-domaine-statique.ngrok.app`.
4. Relance Jarvis. Au démarrage il affiche « Pont iPhone : écoute sur le port 8790 ».
   Teste : `https://ton-domaine.ngrok.app/api/ping` doit répondre `{"ok": true}`.

L'endpoint est **POST `/api/inbox`**, en-tête `X-Jarvis-Token: <ton token>`, corps JSON :
```json
{ "type": "note",     "contenu": "...", "categorie": "idees" }   // categorie optionnelle
{ "type": "commande", "contenu": "eteins les lumieres" }
```
La réponse est un JSON clair (`{"ok": true, "message": "..."}`) que le raccourci affiche.

## 2. Les raccourcis à créer (app Raccourcis)

Pour chacun : **+** (nouveau raccourci) → ajoute les actions ci-dessous. L'action clé
est **« Obtenir le contenu de l'URL »** (Get Contents of URL).

### 🅐 « Note à Jarvis » (dicter/taper une idée)

1. Action **« Demander une entrée »** (Ask for Input) → Type : Texte → invite :
   « Ton idée ? ». (Tu peux dicter au micro.)
2. Action **« Obtenir le contenu de l'URL »** :
   - URL : `https://ton-domaine.ngrok.app/api/inbox`
   - Méthode : **POST**
   - En-têtes : ajoute `X-Jarvis-Token` = `ton token`
   - Corps de la requête : **JSON** →
     `type` = `note` · `contenu` = *la variable « Entrée fournie »* · (`categorie` : laisse vide, Jarvis devine)
3. Action **« Afficher la note »** (Show Result) → *Message* de la réponse.

Renomme-le « Note à Jarvis ». Tu peux l'ajouter à l'écran d'accueil.

### 🅑 « Envoyer à Jarvis » (feuille de partage)

Même chose que 🅐, **mais** :
- Dans les réglages du raccourci (icône ⚙︎), active **« Afficher dans la feuille de
  partage »**, type d'entrée : Texte.
- Au lieu de « Demander une entrée », le `contenu` = la variable **« Entrée du
  raccourci »** (le texte partagé).

Ainsi : surligne un texte n'importe où (Safari, Notes, un message…) → **Partager** →
**« Envoyer à Jarvis »** → c'est noté.

### 🅒 « Dis à Jarvis » (commande à distance)

Comme 🅐, mais `type` = **`commande`**. La phrase dictée (« éteins les lumières »,
« mode film ») est exécutée par Jarvis à la maison.

👉 Astuce : nomme-le exactement **« Dis à Jarvis »**. Tu pourras alors dire à Siri :
**« Dis Siri, Dis à Jarvis, mode film »** → Siri devient ta télécommande à distance.

## 3. Ce que Jarvis fait

- **type `note`** → range la note dans le bon fichier (`idees.md`, `courses.md`,
  `taches.md`…), avec l'heure et la mention « via iPhone ». Jarvis choisit la
  catégorie si tu ne la donnes pas.
- **type `commande`** → traite la phrase comme si tu l'avais dite à voix haute.

Puis, à la maison, à la voix :
- « **Jarvis, sors-moi une idée de contenu** » → il pioche au hasard dans tes idées.
- « **Qu'est-ce que j'ai noté aujourd'hui ?** » → le résumé du jour.

## 🛡️ Sécurité (important)

Une **commande à distance ne peut déclencher que des actions sûres** (lumières,
ambiances/scènes, OBS, minuteurs, stats — les outils domotique/PC). Toute action
sensible (mail, réservation, appel, suppression…) est **refusée** avec « à faire à la
voix à la maison ». Ainsi, **même si ton token était volé**, personne ne pourrait
réserver un resto, envoyer un mail ou passer un appel avec — juste allumer/éteindre
des lumières. Garde quand même ton token secret, et régénère-le au moindre doute.
