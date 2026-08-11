# Déléguer à Hermes (cerveau délibératif)

Jarvis peut confier une **tâche de réflexion / recherche de fond** à
[Hermes Agent](https://github.com/NousResearch/hermes-agent), qui tourne **en local**
sur ta machine, puis t'annoncer le résultat **à voix haute** quand c'est prêt.

- Outil : `deleguer_a_hermes(tache)` — **non exposé via MCP**, **confirmation vocale requise**.
- Phrases déclencheuses : « **délègue à Hermes** … », « **fais une recherche de fond sur** … »,
  « **lance Hermes sur** … ».

> Exemple : « Jarvis, délègue à Hermes : compare les 3 meilleurs micros pour le streaming en 2026. »
> Jarvis : « Je vais déléguer à Hermes : compare les 3 meilleurs micros… Tu confirmes ? » → « oui »
> → « Je délègue ça à Hermes. Je te préviens dès que c'est prêt. » … *(plus tard)* …
> « Hermes a terminé. En résumé : … »

## Comment ça marche

1. Confirmation vocale (l'outil a `confirmation=True`).
2. Jarvis **répond tout de suite** (« je délègue, je te préviens ») et lance la tâche **en
   fond** — il ne te fait pas attendre.
3. En tâche de fond, Jarvis appelle l'**API locale d'Hermes** :
   `POST http://127.0.0.1:8642/v1/responses`, en-tête `Authorization: Bearer <clé>`, corps
   `{"model":"hermes-agent","input":"…","conversation":"jarvis-delegation"}`. Hermes réfléchit
   (et peut utiliser ses propres outils : web, code en conteneur Docker, etc.).
4. Le résultat passe par le **filtre de confidentialité** (`core/confidentialite.py` :
   caviarde mails/clés/numéros/jetons, raccourcit) puis est **lu à voix haute**.
5. **Session persistante** : toutes les délégations partagent la conversation
   `jarvis-delegation` → Hermes garde le contexte d'une délégation à l'autre.

## Configuration (`config.yaml`)

```yaml
hermes:
  api_url: "http://127.0.0.1:8642"   # gateway Hermes, loopback
  api_key: "…"                       # = API_SERVER_KEY du .env d'Hermes
  # api_key_file: "…"                # alternative : un fichier contenant la clé
  session: "jarvis-delegation"       # session persistante
  timeout: 900                       # une recherche de fond peut être longue
  resume_max: 500                    # longueur max du résumé vocal
```

La clé provient du `.env` d'Hermes (`API_SERVER_KEY`). Le serveur API d'Hermes doit tourner
(port 8642, loopback) — il fait partie de la chaîne Hermes (voir `HERMES_NOTES.md` §13, script
`start-hermes-chain.ps1`). Si l'API est éteinte, la délégation échoue proprement (annonce vocale).

## Sécurité

- **Non exposé via MCP** : seule la voix (chez toi) peut déclencher une délégation ; un token
  MCP volé ne peut pas lancer Hermes.
- **Confirmation vocale** avant chaque délégation.
- **Filtre de confidentialité** sur le texte lu à voix haute (dernier garde-fou).
- L'API 8642 est en **loopback** et protégée par la clé `API_SERVER_KEY`.
- Rappel (voir `HERMES_NOTES.md` §14) : Hermes n'a **aucun credential** de tes comptes ; toute
  action sensible reste côté Jarvis avec confirmation. La délégation sert à **réfléchir/chercher**,
  pas à agir sur tes comptes.

## Réglages utiles

- `timeout` : monte-le si tes recherches de fond sont longues (défaut 900 s).
- `resume_max` : longueur du résumé vocal (défaut 500 caractères).
- `session` : change le nom pour repartir d'un contexte vierge.
