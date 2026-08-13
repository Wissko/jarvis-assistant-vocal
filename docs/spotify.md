# Spotify — playlist des musiques reconnues

Quand Jarvis identifie une musique (« c'est quoi cette musique ? »), il peut
l'**ajouter à une playlist Spotify** — à la voix (« ajoute-la à ma playlist ») ou
**automatiquement**. La playlist par défaut : **« Jarvis Finds »** (créée si absente).

## Mise en route (une fois)

### 1. Crée une app Spotify
1. Va sur **https://developer.spotify.com/dashboard** → *Create app*.
2. Note le **Client ID** et le **Client secret**.
3. Dans les *Settings* de l'app, ajoute l'**URI de redirection EXACTE** :
   `http://127.0.0.1:8899/callback`

### 2. `config.yaml`
```yaml
spotify:
  client_id: "ton-client-id"
  client_secret: "ton-client-secret"
  playlist: "Jarvis Finds"     # nom de la playlist cible
  auto_ajout: false            # true = ajout AUTO à chaque musique reconnue
```

### 3. Connexion
```bash
python scripts/spotify_login.py
```
Ton navigateur s'ouvre → autorise. Le **refresh_token** est sauvé dans
`logs/spotify/token.json` (gitignoré) et réutilisé ensuite. Redémarre Jarvis.

## Utilisation

- **À la voix** : après « c'est quoi cette musique ? », dis « **ajoute-la à ma
  playlist** » → l'ajoute à *Jarvis Finds* (évite les doublons).
- **Automatique** : `spotify.auto_ajout: true` → **chaque musique reconnue en direct**
  (micro ou audio système) est ajoutée en tâche de fond, sans rien dire. *(L'ajout
  auto ne s'applique PAS à l'identification d'un fichier — seulement aux découvertes
  live.)*
- Titre précis : « ajoute *Blinding Lights* de The Weeknd à ma playlist ».

## Les outils

| Outil | Niveau | MCP | Effet |
|---|---|---|---|
| `ajouter_a_playlist` | N1 | non | ajoute la dernière musique reconnue (ou un titre donné) |

## Sécurité / vie privée

- `client_secret` et le **refresh_token** sont des secrets : `config.yaml` et
  `logs/` sont **gitignorés**. Scopes demandés : `playlist-modify-private/public` et
  `playlist-read-private` (pour retrouver/créer la playlist) — rien d'autre.
- Non exposé au MCP : Hermes/le réseau ne peuvent pas toucher à ta playlist.
- API **officielle** Spotify (contrairement à Alexa) : stable, ne « casse » pas.
