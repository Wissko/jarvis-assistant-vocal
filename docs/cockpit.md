# Cockpit (tableau de bord perso)

Une **app web locale** servie par le serveur unifié de Jarvis, ouverte en **fenêtre
app** (`--app`, sans barre de navigateur) sur l'écran de ton choix. **Local-only** par
défaut (même garde que le panneau) : rien ne sort, aucune donnée exposée au MCP.

> **Doctrine** : Jarvis détient les clés et le corps — **toutes les données restent
> locales** (`finances/`, gitignoré). Hermes ne reçoit que des **agrégats**, sur
> demande (bilan mensuel — phase ultérieure). **Jamais** de credentials bancaires,
> **aucune** API d'agrégation.

## Activer

```yaml
cockpit:
  actif: true
  ecran: 0          # 0 = principal, 1 = 2e écran…
  navigateur: ""    # chemin chrome/edge ; vide = auto-détection
```

Au démarrage de Jarvis, le cockpit s'ouvre en fenêtre app. Sinon, à la main :
`http://localhost:8790/cockpit` (accessible uniquement depuis ce PC).

## Volet Finances (Phase 1 — disponible)

Copie l'exemple puis édite-le :
```
finances/abonnements.example.yaml  →  finances/abonnements.yaml
```
Chaque abonnement : `service`, `montant` (€), `periodicite` (mensuel / annuel /
trimestriel / semestriel / hebdomadaire), `jour` (jour du mois, pour le mensuel) **ou**
`date` (AAAA-MM-JJ d'ancrage), `categorie`.

Le cockpit affiche :
- **Total mensuel** (les annuels/trimestriels sont ramenés au mois) et l'équivalent annuel ;
- **Timeline des prochaines échéances** (triée), avec « demain / dans N j » ;
- **Alertes** : ⏰ **prélèvement demain**, 🔔 **montant changé** (comparé à la dernière
  valeur vue) ;
- **Répartition par catégorie**.

### Détection automatique par mail (recommandé)

« **Jarvis, détecte mes abonnements** » (`detecter_abonnements`) : scanne tes **reçus
Gmail** (Apple, Netflix, Spotify, Adobe…) des derniers mois, en déduit service +
montant + périodicité, et écrit une **proposition** dans
`finances/abonnements_detectes.yaml` (revue, jamais d'écrasement). Puis « **intègre-les** »
(`integrer_abonnements_detectes`, **confirmation**) les ajoute à `abonnements.yaml`
sans toucher à tes entrées manuelles.

Avantages (fidèle à la doctrine) : **aucun credential bancaire, aucune API
d'agrégation** — ça passe par ton Gmail déjà connecté (IMAP), 100 % local. Attrape
même les **abonnements Apple** (que le relevé bancaire regroupe en une seule ligne).
C'est **heuristique** → d'où la revue avant intégration.

*(Import CSV bancaire + dépenses/rentrées ponctuelles : Phase 1b suivante.)*

## À venir (phases suivantes)

- **⚡ Énergie** : prise **Tapo P110** (API locale — conso PC temps réel), puis Linky
  via un relais gratuit type MyElectricalData (Enedis DataConnect est réservé aux pros).
  Octopus France n'a pas d'API publique.
- **📈 Réseaux** : Insta (tokens existants), Twitch/YouTube plus tard.
- **🎬 Contenu** : pipeline `contenus.yaml`, deadlines Loopstr, inspirations du Vault.
- **🏠 Maison/Système** : liens vers `/panneau` (état chaîne, budgets) — intégré, pas dupliqué.
- **🧠 Bilan mensuel Hermes** : cron optionnel → Hermes reçoit les **agrégats** →
  analyse envoyée sur Telegram.

## Vie privée

- Dossier `finances/` **entièrement gitignoré** (seul `abonnements.example.yaml` est
  versionné) — rien ne part vers le repo public.
- **Accès distant désactivé** par défaut (garde local-only). Activation distante
  (avec token) réservée à une phase ultérieure si tu veux le cockpit sur le téléphone.
- Aucune donnée financière n'est exposée au MCP ni envoyée à Hermes, sauf agrégats sur demande.
