# Éteindre le PC & le réveiller (Wake-on-LAN)

**Doctrine — 100 % Jarvis (physique, règle N3).** Éteindre le PC est une action
**critique** : Jarvis la fait **à la voix, à la maison**, avec confirmation N3 et un
délai annulable. Le **réveil**, lui, ne peut pas venir de Jarvis (un PC éteint
n'exécute plus rien 😄) : c'est le **Wake-on-LAN** (WOL), un « magic packet » envoyé
par un appareil qui, lui, est allumé — **ton iPhone**.

---

## 1. Éteindre : côté Jarvis (déjà en place)

- Dis **« Jarvis, éteins le PC »** → Jarvis **demande confirmation** (N3), coupe
  d'abord les **lumières** (scène `assistant.scene_extinction`, défaut `off`), puis
  programme l'arrêt avec un **délai annulable** (`assistant.delai_extinction`, défaut
  30 s).
- Pendant le délai : dis **« annule l'extinction »** → l'arrêt est annulé
  (`shutdown /a`). Le PC reste allumé.
- **Jamais à distance** : `eteindre_pc` est N3 (non exposé au MCP, refusé depuis le
  pont iPhone, non mémorisable en « toujours autoriser »).

```yaml
# config.yaml
assistant:
  scene_extinction: "off"    # scène lumières jouée avant l'arrêt
  delai_extinction: 30       # secondes avant l'arrêt (annulable)
```

---

## 2. Réveiller : Wake-on-LAN

Trois couches doivent être bonnes **en même temps** : **Windows**, la **carte
réseau**, et le **BIOS**. Puis on envoie le magic packet depuis l'iPhone.

### 2.1 Trouver l'adresse MAC de ta carte réseau (à noter)

Dans une invite Windows :

```bash
getmac /v /fo list
```

Repère l'adaptateur **Ethernet** connecté (« Connexion réseau » / « Ethernet ») et
note son **Adresse physique** (format `XX-XX-XX-XX-XX-XX`). *(WOL passe par le
câble Ethernet — le Wi-Fi ne réveille pas de façon fiable.)*

### 2.2 Windows — désactiver le « démarrage rapide » ⚠️ (le point n°1)

Le **démarrage rapide** (Fast Startup) fait une extinction **hybride** (proche de la
veille prolongée) : sur beaucoup de cartes, le WOL **ne s'arme pas** dans cet état.
**Désactive-le** pour que le WOL marche depuis une extinction complète :

1. Panneau de configuration → **Options d'alimentation** → « Choisir l'action des
   boutons d'alimentation ».
2. Clique **« Modifier des paramètres actuellement non disponibles »**.
3. Décoche **« Activer le démarrage rapide (recommandé) »** → Enregistrer.

*(Équivalent en ligne de commande : `powercfg /h off` désactive l'hibernation **et**
le démarrage rapide — mais supprime aussi la veille prolongée. La case à décocher
est plus fine.)*

### 2.3 Carte réseau — réglages du pilote (Gestionnaire de périphériques)

Gestionnaire de périphériques → **Cartes réseau** → *(ton adaptateur Ethernet :
Intel I219-V / I225-V ou Realtek RTL8125…)* → **Propriétés** :

- Onglet **Gestion de l'alimentation** :
  - ✅ « Autoriser ce périphérique à sortir l'ordinateur du mode veille »
  - ✅ « Autoriser uniquement un paquet magique à sortir l'ordinateur du mode veille »
- Onglet **Avancé** (noms selon Intel/Realtek) :
  - **Wake on Magic Packet** (Réveil par paquet magique) = **Activé**
  - **Wake on Magic Packet from power off state** / **Shutdown Wake-On-Lan** =
    **Activé** *(indispensable pour réveiller depuis un PC éteint, pas seulement en veille)*
  - **Wake on Pattern Match** (Réveil par correspondance de motif) = **Désactivé**
    *(évite les réveils intempestifs)*
  - **Energy Efficient Ethernet** (EEE) / **Green Ethernet** = **Désactivé**
    *(l'économie d'énergie coupe parfois le lien en veille → WOL raté)*

### 2.4 BIOS MSI Z490 (Click BIOS 5)

Redémarre, appuie sur **Suppr** pour entrer dans le BIOS, passe en **mode avancé
(F7)** :

- **Settings → Advanced → Power Management Setup → « ErP Ready » = Disabled.**
  ⚠️ Le plus important : **ErP/EuP activé coupe l'alimentation de veille (+5 V SB)**
  en S4/S5 → la carte réseau n'est plus alimentée → **aucun WOL possible depuis
  l'extinction**. Il **doit** être sur *Disabled*.
- **Settings → Advanced → Wake Up Event Setup → « Resume By PCI-E Device » = Enabled**
  *(couvre la carte réseau intégrée ; sur certains BIOS c'est « Resume by PCIe/Onboard LAN »)*.
- Enregistre et quitte (**F10**).

---

## 3. Veille hybride Windows vs WOL — les réglages qui marchent vraiment

| État Windows | WOL possible ? | Condition |
|---|---|---|
| **Veille (S3)** | ✅ oui | carte réseau « Wake on Magic Packet » activé |
| **Extinction complète (S5)** | ✅ oui | **Fast Startup désactivé** + **ErP Disabled** + carte « Shutdown Wake-On-Lan » activé |
| **Démarrage rapide (Fast Startup, ~S4)** | ❌ souvent non | c'est le piège : **désactive-le** (§2.2) pour retomber en vrai S5 |
| **Veille prolongée / hibernation (S4)** | ⚠️ variable | seulement si la carte gère le réveil depuis S4/S5 + ErP Disabled ; sinon, préfère la **veille (S3)** |

**Config qui marche de façon fiable (recommandée) :**
1. **Démarrage rapide désactivé** (§2.2).
2. **ErP Ready = Disabled** au BIOS (§2.4).
3. Carte réseau : **magic packet + shutdown-WOL activés, EEE désactivé** (§2.3).

→ Avec ça, le WOL fonctionne **depuis la veille (S3) ET depuis l'extinction
complète (S5)**.

**Diagnostic utile** (invite Windows) :
```bash
powercfg /a                       # états de veille disponibles
powercfg -devicequery wake_armed  # périphériques autorisés à réveiller
powercfg /lastwake                # ce qui a réveillé le PC la dernière fois
```
Si la carte réseau n'apparaît pas dans `wake_armed`, reprends §2.3.

---

## 4. Envoyer le magic packet depuis l'iPhone (le plus simple)

iOS ne sait pas envoyer de paquet UDP brut nativement → on passe par une **app WOL
gratuite**, la plus simple étant **Mocha WOL**.

1. **App Store → installe « Mocha WOL »** (gratuit).
2. Ajoute un appareil :
   - **Nom** : PC
   - **MAC address** : celle notée au §2.1 (`XX-XX-XX-XX-XX-XX`)
   - **Broadcast / IP** : `255.255.255.255` *(ou l'adresse de diffusion de ton
     réseau, ex. `192.168.1.255`)*
   - **Port** : `9` *(ou `7`)*
3. **Réveil en 1 tap** : ouvre Mocha WOL → tape sur « PC ». Le PC démarre.

**Depuis un Raccourci / Siri** : Mocha WOL fournit une **action Raccourcis**
(« Wake »). Crée un Raccourci → ajoute l'action **Mocha WOL** → choisis l'appareil
« PC » → nomme-le **« Réveille le PC »**. Tu pourras dire *« Dis Siri, réveille le
PC »*. *(Si ta version de l'app n'expose pas l'action Raccourcis, utilise le
**widget** Mocha WOL sur l'écran d'accueil, ou ouvre l'app — un tap suffit.)*

> **À la maison uniquement.** Le WOL est une **diffusion réseau local** (couche 2) :
> l'iPhone doit être sur **le même Wi-Fi/LAN** que le PC. Depuis l'extérieur, il faut
> une redirection de port UDP vers l'adresse de diffusion sur ta box (souvent bloquée)
> ou un relais WOL — c'est un montage avancé, hors périmètre ici.

---

## 5. Test de bout en bout

1. **Éteins** : *« Jarvis, éteins le PC »* → confirme → les lumières s'éteignent, le
   PC s'arrête après le délai. *(Ou teste `shutdown /s /t 30` puis `shutdown /a`.)*
2. Attends que le PC soit **complètement éteint** (voyant carte réseau souvent
   encore allumé = bon signe : la carte est alimentée en veille).
3. **Réveille** : tape « PC » dans Mocha WOL (iPhone sur le Wi-Fi maison) → le PC
   démarre.
4. Si rien ne se passe : reprends **§2.2 (Fast Startup)** puis **§2.4 (ErP)** — ce
   sont les deux causes d'échec les plus fréquentes.

*(Pour tester le WOL sans l'iPhone, depuis un autre PC allumé du réseau, en
PowerShell : construis le magic packet — 6 octets `0xFF` + 16× la MAC — et envoie-le
en UDP broadcast sur le port 9.)*
