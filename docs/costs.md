# Coûts, budgets & routage (N12)

> **Doctrine** : Hermes orchestre et pense ; Jarvis détient les clés et le corps.
> Le routage ci-dessous **est** l'implémentation de la doctrine — qui fait quoi, et à
> quel coût.

## Les 4 backends (config `mode`)

| Mode | LLM | Voix | Pour quoi |
|---|---|---|---|
| **local** | Ollama | Piper/Kokoro | tout local, **rien ne sort**, gratuit |
| **hybride** *(défaut)* | Claude éco (`anthropic.modele`) | ElevenLabs | réflexes (domotique, timers, scènes, questions courtes) + vision/navigateur/résa en cloud ; **tâches de fond → Hermes** |
| **qualite** | Claude fort (`anthropic.modele_qualite`) | ElevenLabs | cloud partout, meilleur raisonnement |

*(L'ancien `mode: cloud` reste accepté = `hybride`.)* Changement **à la voix** :
« passe en local », « repasse en hybride », « mode qualité » (`mode_routage`).

**Routage vers Hermes** : en hybride, une **tâche de fond** (analyse, recherche
longue, veille) est confiée à Hermes via `deleguer_a_hermes` — le modèle l'appelle
de lui-même (« je confie ça à Hermes »), plus besoin de le dire. Les réflexes
restent sur le chemin court de Jarvis (rapide, économique).

## Suivi des coûts (centralisé, persisté)

Compteurs par fournisseur, agrégés **jour / mois**, dans `budget.json` (non versionné) :

- **Claude (Jarvis)** : chaque appel instrumenté (tokens in/out + cache), coût via
  `budget.prix` (tarifs Anthropic $/Mtok).
- **Voix ElevenLabs** : facturée au caractère → `budget.prix_elevenlabs` ($/1000 car.).
- **Twilio** (appels) : compteur mensuel `logs/calls/compteur.json`.
- **Hermes** : tient **sa propre** compta (`hermes insights`) — Jarvis la lit mais ne
  la double pas ; la part d'Hermes est affichée à part (tokens).

À la voix : « **mon budget ?** » → réponse ventilée (coût jour/mois, par poste, % du
plafond, + tokens Hermes). Aussi visible dans le **panneau → État**.

## Budgets & garde-fous (jamais de blocage silencieux)

Dans `config.yaml → budget` :

```yaml
budget:
  plafond_jour: 2.0        # $/jour (null = pas de plafond)
  plafond_mois: 30.0       # $/mois
  alerte_pct: 80           # alerte VOCALE à 80 % du plafond
  mode_normal: hybride     # mode repris le lendemain après une bascule auto
  crons_critiques: []      # crons Hermes jamais suspendus (ex: ["reveil"])
```

- **80 %** d'un plafond → **alerte vocale** (« j'ai dépensé 80 % de mon plafond du
  jour, il reste ~X dollars »), une fois par jour.
- **Plafond atteint** → **bascule automatique en local** (Ollama + Piper, gratuit)
  avec annonce claire, **+ suspension des crons Hermes non critiques** jusqu'au
  lendemain. **Le lendemain** : budget réarmé, crons repris, retour au `mode_normal`
  — automatiquement.
- Un **changement manuel** de mode désarme la bascule auto (tu décides).

## Coûts typiques (ordres de grandeur, à titre indicatif)

*Estimations — dépendent de tes modèles/offres. Ajuste `budget.prix*`.*

| Usage | Backend | Coût approx. |
|---|---|---|
| Commande domotique / timer / scène | hybride (Haiku) | ~0,001–0,003 $ |
| Question courte parlée (réponse ElevenLabs ~200 car.) | hybride | ~0,02 $ (voix) + LLM |
| Question avec vision (capture d'écran) | hybride | ~0,01–0,03 $ |
| Analyse / recherche de fond | Hermes | plus élevé (modèle fort, longue) |
| Appel téléphonique | Twilio | ~0,02 $/min + voix |
| Tout en **local** | Ollama + Piper | **0 $** |

Pour ne rien dépenser : `mode: local` (ou « passe en local »). Pour la qualité
maximale ponctuelle : « mode qualité », puis « repasse en hybride ».
