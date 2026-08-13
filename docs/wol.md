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

### 2.1 Choix de la prise — **API LOCALE obligatoire** (pas de cloud chinois)

Cohérence doctrine (local-first) **et** pour que Jarvis puisse la piloter un jour
directement : choisis une prise avec **API locale documentée**, pas une prise 100 %
cloud (Tuya générique, Meross…).

| Prise | API locale | Pourquoi |
|---|---|---|
| **Shelly Plug S / Plus Plug S** *(recommandée)* | **REST HTTP local** natif, sans cloud, MQTT dispo | Marque européenne (Allterco), API la plus simple à piloter (`http://<ip>/relay/0?turn=on`), mesure la conso. ~15-20 € |
| **TP-Link Kasa** (KP105) / **Tapo** (P110) | Protocole local via la lib `python-kasa` | Grand public, pas cher, dispo partout ; local exploitable sans cloud |
| **Prise pré-flashée Tasmota** (Athom, Nous A1T) | **HTTP local** open-source (`/cmnd?cmnd=Power%20On`) | 100 % libre, zéro cloud — idéal doctrine si tu acceptes une marque plus niche |

→ **Recommandation : Shelly Plug S** (API REST locale la plus propre pour la future
intégration Jarvis). **À éviter** : les prises no-name « Smart Life / Tuya » 100 %
cloud, et Meross (local bancal).

> Mets une **réservation DHCP** dans ta box pour la prise (par sa MAC) → son IP ne
> bouge plus, les raccourcis et Jarvis la trouvent toujours.

### 2.2 BIOS MSI Z490 (Click BIOS 5)

Entre dans le BIOS (**Suppr** au démarrage), mode avancé (**F7**) :

- **Settings → Advanced → Power Management Setup → « Restore after AC Power Loss »
  = Power On.**

→ Désormais, **chaque fois que le courant revient**, le PC démarre tout seul.
Enregistre et quitte (**F10**).

### 2.3 Câblage

Alim du PC (bloc secteur) → **prise connectée** → mur. **Laisse la prise sur ON** en
temps normal (le PC doit avoir du courant). Le rallumage = **couper puis rétablir**
le courant.

### 2.4 Raccourci Siri « Rallume le PC » + 🛡️ GARDE-FOU

⚠️ **Danger** : couper le courant d'un PC **allumé ou en veille** = arrêt brutal
(risque de corruption). On ne coupe **QUE** si le PC est **vraiment éteint** (après
« Jarvis éteins le PC »).

Raccourci (app **Raccourcis**), en **local** sur ton Wi-Fi :

1. **🛡️ Garde-fou — Demander confirmation** (action « Demander une confirmation ») :
   texte *« Le PC est-il bien ÉTEINT ? Ne pas couper la prise s'il tourne ou dort. »*
   → si **Annuler**, le raccourci s'arrête.
2. **Couper** — « Obtenir le contenu de l'URL » :
   - Shelly Gen1 : `http://IP-DE-LA-PRISE/relay/0?turn=off`
   - Shelly Gen2 (Plus) : `http://IP-DE-LA-PRISE/rpc/Switch.Set?id=0&on=false`
3. **Attendre** 4 secondes (action « Attendre »).
4. **Rétablir** — « Obtenir le contenu de l'URL » :
   - Shelly Gen1 : `http://IP-DE-LA-PRISE/relay/0?turn=on`
   - Shelly Gen2 : `http://IP-DE-LA-PRISE/rpc/Switch.Set?id=0&on=true`
5. **Notifier** — « Afficher une notification » : *« Le PC démarre. »*

Nomme-le **« Rallume le PC »** → *« Dis Siri, rallume le PC »*.
*(iPhone sur le **même Wi-Fi** que la prise : l'appel est 100 % local, aucun cloud.)*

**Consigne (règle d'or)** : n'utilise **« Rallume le PC »** **que** quand le PC est
éteint. Ne coupe **jamais** la prise pendant qu'il tourne ou qu'il est en veille.

### 2.5 🛡️ Garde-fou côté Jarvis (quand Jarvis pilotera la prise, plus tard)

Le jour où on branche la prise à Jarvis (via son **API locale** — d'où le choix
2.1), l'outil `rallumer_pc` devra **refuser de couper la prise si le PC répond au
ping** (preuve qu'il est allumé). Design cible :

```text
rallumer_pc():
    si ping(IP_du_PC) répond      -> "Le PC répond déjà, je ne touche pas à la prise."
    sinon (PC injoignable = éteint):
        POST prise OFF (API locale)   # ex. http://IP-prise/relay/0?turn=off
        attendre 4 s
        POST prise ON                 # http://IP-prise/relay/0?turn=on
        -> "Courant rétabli, le PC démarre."
```

Ce garde-fou par ping est **la raison** d'exiger une prise à **API locale** : Jarvis
doit pouvoir couper/rétablir **et** vérifier l'état sans dépendre d'un cloud. *(Non
codé pour l'instant : à faire quand la prise est là et son IP connue.)*

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

## 4. Test de bout en bout (prise connectée)

1. **Éteins** : *« Jarvis, éteins le PC »* → confirme → lumières off + arrêt.
2. Attends que le PC soit **complètement éteint**.
3. **Rallume** : lance **« Rallume le PC »** (iPhone sur le Wi-Fi maison) → confirme
   qu'il est bien éteint → la prise coupe puis rétablit → le PC **démarre**.
4. Si rien : vérifie le BIOS **« Restore after AC Power Loss = Power On »** (§2.2) et
   que l'IP de la prise dans le raccourci est la bonne.
