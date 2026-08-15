# Éteindre le PC & le rallumer à distance

**Doctrine — 100 % Jarvis (physique, règle N3).** Éteindre le PC est une action
**critique** : Jarvis la fait **à la voix, à la maison**, confirmation N3 + délai
annulable. Le **rallumage** ne peut pas venir de Jarvis (un PC éteint n'exécute plus
rien 😄) : on le déclenche depuis un appareil allumé — **ton iPhone**.

Contrainte matérielle constatée : ta connexion est un **dongle Wi-Fi USB** (coupé à
l'extinction → **pas de Wake-on-LAN possible**) et le port Ethernet est débranché.
La solution retenue, sans câble qui traverse la pièce : une **prise connectée
pilotable en local** + le BIOS réglé pour démarrer au retour du courant.

---

## 1. Éteindre : côté Jarvis (déjà en place)

- Dis **« Jarvis, éteins le PC »** → confirmation **N3**, coupe d'abord les
  **lumières** (scène `assistant.scene_extinction`, défaut `off`), puis arrêt avec
  **délai annulable** (`assistant.delai_extinction`, défaut 30 s).
- Pendant le délai : **« annule l'extinction »** → `shutdown /a`, le PC reste allumé.
- **Jamais à distance** : `eteindre_pc` est N3 (non exposé au MCP, refusé depuis le
  pont iPhone, non mémorisable en « toujours autoriser »).

```yaml
# config.yaml
assistant:
  scene_extinction: "off"    # scène lumières jouée avant l'arrêt
  delai_extinction: 30       # secondes avant l'arrêt (annulable)
```

---

## 2. Rallumer sans câble : prise connectée pilotable en local ✅

**Principe** : le PC démarre **au retour du courant**, et tu pilotes le courant
depuis l'iPhone via une prise Wi-Fi. Aucun réseau requis sur le PC.

### 2.1 Prise retenue : **Tapo P110** ✅ (installée)

**Installée** : une **TP-Link Tapo P110** (grand public, ~15 €, **mesure la conso** —
c'est elle qui alimentera le volet Énergie du Cockpit). Pilotable **en local** via
la lib Python `python-kasa` (≥ 0.7, protocole **KLAP**) ou `plugp100`.

> ⚠️ Particularité Tapo (vs Shelly) : **pas d'URL HTTP simple**. Le protocole local
> KLAP exige les **identifiants du compte Tapo** (email + mot de passe) même pour un
> appel 100 % local — ils servent au handshake de chiffrement, rien ne part vers le
> cloud une fois la clé négociée. Ces identifiants iront dans `config.yaml`
> (gitignoré) le jour de l'intégration Jarvis. *(Une Shelly aurait donné une API REST
> plus simple — `http://<ip>/relay/0?turn=on` — mais la P110 fait le job et mesure la
> conso, ce que toutes les Shelly ne font pas.)*

**Réglages faits :**
- **Nom de la prise : « Tour PC »** (dans l'app Tapo).
- **Réservation DHCP** conseillée dans la Bbox (par la MAC de la P110) → son IP ne
  bouge plus, comme pour l'ESP32 amaran. *(À faire si pas encore fait — même méthode :
  mabbox → appareils → la P110 → IP fixe.)*

### 2.2 BIOS MSI Z490 (Click BIOS 5)

Entre dans le BIOS (**Suppr** au démarrage), mode avancé (**F7**) :

- **Settings → Advanced → Power Management Setup → « Restore after AC Power Loss »
  = Power On.**

→ Désormais, **chaque fois que le courant revient**, le PC démarre tout seul.
Enregistre et quitte (**F10**). **Réglé et testé ✅.**

### 2.3 Câblage (fait ✅)

**Tour PC → Tapo P110 « Tour PC » → multiprise → mur.** La P110 est intercalée
**entre la multiprise et la tour** : elle ne coupe **que le PC**, pas le reste du
setup (écrans, lampe, amaran…). **Laisse-la sur ON** en temps normal (le PC doit
avoir du courant en permanence). Rallumage = **couper puis rétablir** via la P110.

### 2.4 Rallumage sans PC : côté iPhone (app Tapo)

⚠️ **Danger inchangé** : couper le courant d'un PC **allumé ou en veille** = arrêt
brutal (risque de corruption). On ne coupe **QUE** si le PC est **vraiment éteint**
(après « Jarvis éteins le PC »).

La P110 **n'est pas HomeKit** → pas de raccourci « Obtenir l'URL » comme pour une
Shelly. En attendant l'intégration Jarvis (§2.5) :

1. **App Tapo** → prise « Tour PC » → **OFF**, attendre ~4 s, **ON**. Le PC démarre
   (BIOS Restore = Power On). ✅ **Cycle validé.**
2. **Voix (option)** : l'app Tapo peut exposer « Tour PC » à **Siri / Raccourcis**
   (réglages de la prise → *Raccourcis Siri*) → « Dis Siri, allume Tour PC ». ⚠️ Ce
   raccourci natif **n'a pas de confirmation** — discipline manuelle obligatoire :
   ne l'utilise **que** PC éteint.

**Règle d'or** : ne coupe **jamais** la prise pendant que le PC tourne ou dort.

### 2.5 🛡️ Garde-fou côté Jarvis (backlog — voir §5)

Le jour où on branche la P110 à Jarvis (lib **`python-kasa`** ≥ 0.7 / `plugp100`, IP
fixe + identifiants Tapo dans `config.yaml`), l'outil `rallumer_pc` devra **refuser de
couper la prise si le PC répond au ping** (preuve qu'il est allumé). Design cible :

```text
rallumer_pc():
    si ping(IP_du_PC) répond      -> "Le PC répond déjà, je ne touche pas à la prise."
    sinon (PC injoignable = éteint):
        P110.turn_off()               # via python-kasa (KLAP local)
        attendre 4 s
        P110.turn_on()
        -> "Courant rétabli, le PC démarre."
```

Ce garde-fou par ping est **la raison** d'exiger une prise à **API locale** : Jarvis
doit pouvoir couper/rétablir **et** vérifier l'état sans dépendre d'un cloud. *(Non
codé : backlog §5.)*

---

## 3. Alternative filaire : Wake-on-LAN (si un jour tu câbles)

Si tu passes en **Ethernet filaire** (câble direct **ou** adaptateurs **CPL /
Powerline** — Ethernet par le réseau électrique, sans fil qui traverse), le vrai
Wake-on-LAN devient possible et plus « propre ». Réglages qui marchent :

- **MAC de la carte Ethernet** (`getmac /v /fo list`, format `XX-XX-XX-XX-XX-XX`) —
  la Realtek PCIe 2.5GbE de la carte mère.
- **Windows** : désactiver le **démarrage rapide** (Options d'alimentation → « Choisir
  l'action des boutons » → décocher « Activer le démarrage rapide ») — sinon le WOL
  ne s'arme pas depuis l'extinction.
- **Carte réseau** (Gestionnaire de périphériques → onglet Avancé) : **Wake on Magic
  Packet = Activé**, **Shutdown Wake-On-Lan = Activé**, **Wake on Pattern Match =
  Désactivé**, **Energy Efficient Ethernet = Désactivé** ; onglet Gestion de
  l'alimentation : ✅ « autoriser… paquet magique ».
- **BIOS** : **ErP Ready = Disabled** (sinon plus d'alim carte réseau en veille) +
  **Resume By PCI-E Device = Enabled**.
- **Compatibilité veille** : WOL OK depuis **veille (S3)** et **extinction (S5)** une
  fois Fast Startup désactivé + ErP Disabled ; le **démarrage rapide (~S4)** est le
  piège n°1. `powercfg -devicequery wake_armed` doit lister la carte.
- **iPhone** : app **Mocha WOL** (magic packet) → MAC ci-dessus, broadcast
  `192.168.1.255`, port `9`. WOL = réseau local → **à la maison uniquement**.

---

## 4. Test de bout en bout (Tapo P110)

1. **Éteins** : *« Jarvis, éteins le PC »* → confirme → lumières off + arrêt.
2. Attends que le PC soit **complètement éteint**.
3. **Rallume** : app Tapo → « Tour PC » **OFF** → ~4 s → **ON** (ou raccourci Siri) →
   le PC **démarre**. ✅ **Validé.**
4. Si rien : vérifie le BIOS **« Restore after AC Power Loss = Power On »** (§2.2).

---

## 5. Backlog — intégration Jarvis de la Tapo P110

**Non codé — à faire.** Deux usages, une seule intégration (`python-kasa` / `plugp100`,
IP fixe + identifiants Tapo dans `config.yaml` gitignoré, `mcp_expose=False` — physique,
reste local, jamais Hermes) :

1. **Conso temps réel → Cockpit N16 (Énergie)** : lire `get_energy_usage()` de la P110
   (puissance instantanée en W, kWh du jour/mois) → alimente le volet Énergie du
   Cockpit (conso du setup en direct). Cf. [cockpit.md](cockpit.md).
2. **Outil `rallumer_pc` avec garde-fou ping** (§2.5) : refuse de couper la prise si
   le PC répond au ping. N1/N2, jamais N3 par erreur — mais un cycle prise reste une
   action physique sensible → confirmation.

⚠️ Rappel doctrine : couper la prise est **dangereux si le PC tourne** → le ping est
non négociable dans l'implémentation.
