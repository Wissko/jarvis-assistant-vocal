# Alexa / Amazon Echo (⚠️ Expérimental)

> **⚠️ Expérimental — via `alexapy`, une lib communautaire non officielle.** Ça
> **fonctionne** (c'est ce qu'utilise Home Assistant), mais l'accès repose sur une
> connexion au compte Amazon par cookie : **fragile**, Amazon peut le casser à tout
> moment. Retours bienvenus via les
> [issues](https://github.com/sosoj92/jarvis-assistant-vocal/issues).

## Le choix d'API et ses limites (honnête)

Amazon n'a **aucune API officielle** pour *piloter* tes appareils Alexa depuis un
tiers. La seule voie viable est **`alexapy`** : login sur ton compte Amazon (cookie +
2FA), puis pilotage des **Echo**. Conséquences :

- ✅ Faire **parler** un Echo (annonce / TTS), contrôler le **média** (play/pause/volume),
  **lister** les Echo, et **déclencher une Routine**.
- 🔁 **Contrôle des appareils (lumières, prises…) = indirect, via Routines.** Tu crées
  dans l'app Alexa une routine avec un énoncé (« lumière salon on ») qui fait l'action,
  et Jarvis la déclenche par son nom. C'est le contournement standard (pas de contrôle
  direct on/off/luminosité par API).
- ⚠️ **Fragile** : si Amazon change son login, l'accès casse → relancer la connexion.

## Les outils

| Outil | Niveau | Effet |
|---|---|---|
| `alexa_etat` | N1 | Liste les Echo + en ligne / hors ligne |
| `alexa_annoncer` | N1 | Fait parler un Echo (TTS sur un appareil, ou annonce sur tous) |
| `alexa_media` | N1 | play / pause / volume sur un Echo |
| `alexa_routine` | **N2** | Déclenche une Routine par son énoncé *(confirmation — une routine peut être impactante)* |

---

## Mise en route

### 1. 2FA Amazon (fortement recommandé)
Active la **validation en deux étapes** sur ton compte Amazon avec une **appli
d'authentification** (pas seulement SMS). Lors de la configuration, Amazon affiche une
**clé secrète** (la « graine » TOTP, une longue chaîne). **Note-la** : mise dans
`alexa.otp_secret`, `alexapy` génère le code 2FA tout seul → reconnexion sans
intervention. *(Sans elle, tu devras saisir le code 2FA à chaque reconnexion.)*

### 2. `config.yaml`
```yaml
alexa:
  email: "ton.email@exemple.fr"
  password: "ton-mot-de-passe-amazon"
  otp_secret: "LA-GRAINE-TOTP"     # optionnel mais recommandé
  url: "amazon.fr"                 # ou amazon.com, amazon.de...
```

### 3. Connexion interactive (une fois)
```bash
python scripts/alexa_login.py
```
Gère le **captcha** et le **2FA** en interactif, puis **sauvegarde le cookie** (dans
`logs/alexa/`, gitignoré). Les outils Alexa réutilisent ce cookie ensuite. Redémarre
Jarvis : **« Jarvis, mes appareils Alexa »**.

### 4. Contrôler tes lumières via des Routines
Dans l'app **Alexa → Routines → +** : crée une routine, déclencheur **« Quand vous
dites… »** (ex. `lumière salon on`), action **« Maison connectée »** → allumer la
lampe. Ensuite : **« Jarvis, lance la routine lumière salon on »**.

---

## Dépannage

- **« Connexion Alexa requise »** dans un outil → relance `python scripts/alexa_login.py`
  (le cookie a expiré ou l'auth a changé).
- **Captcha en boucle** → connecte-toi d'abord au site Amazon dans un navigateur
  (même IP), puis relance le script.
- **2FA demandé à chaque fois** → renseigne `alexa.otp_secret` (graine TOTP).
- **`amazon.com` vs `amazon.fr`** → mets le **domaine de ton compte** dans `alexa.url`.
- **Rien ne parle** → l'appareil ciblé n'est pas un Echo « qui parle », ou hors ligne
  (`alexa_etat` pour vérifier).

## Sécurité

Identifiants **uniquement dans `config.yaml`** (gitignoré) ; le cookie de session est
sous `logs/` (gitignoré). Traite `password` et `otp_secret` comme des secrets. Les
outils sont **N1/N2** (jamais N3) et **non exposés au MCP** — Alexa n'est pas pilotable
à distance ni par Hermes.
