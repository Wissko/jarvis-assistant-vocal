# TBS Workspace et Lowkey

TBS Workspace est la source de vérité opérationnelle de Lowkey pour l'agence TO
BE SEEN. `businesses.yaml` décrit le portefeuille stable; l'API TBS fournit les
données vivantes: clients, projets, tâches, réunions, notes, factures et
abonnements.

## Connexion

1. Déployer la version à jour de `Wissko/tbs-workspace` et appliquer son fichier
   `supabase/schema.sql`.
2. Générer un secret aléatoire d'au moins 32 caractères.
3. Ajouter ce secret dans l'environnement du déploiement TBS sous
   `LOWKEY_SERVICE_TOKEN`.
4. Reporter le même secret dans le `config.yaml` local de Lowkey:

```yaml
tbs:
  api_url: "https://ton-deploiement-tbs/api/lowkey"
  service_token: "le-meme-secret"
  timeout: 6
  cache_seconds: 45
```

Le secret reste dans deux emplacements non versionnés: l'environnement du
serveur TBS et le `config.yaml` local.

## Utilisation

- « Lowkey, donne-moi le brief business TBS. »
- « Quelles sont mes trois priorités aujourd'hui ? »
- « Ajoute une tâche Relancer le client dans Loyalty Pass pour demain. »
- « Ajoute cette décision aux notes du projet TBS Website. »

Les lectures sont automatiques. La création d'une tâche ou d'une note demande
une confirmation vocale. Lowkey ne peut pas modifier les clients, factures,
abonnements ou finances par cette API.

Si l'API n'est pas configurée ou indisponible, Lowkey conserve la carte statique
du portefeuille et signale clairement que les données CRM en temps réel ne sont
pas accessibles.
