# XTTS v2 local de Lowkey

Lowkey utilise XTTS v2 uniquement sur `127.0.0.1:8020`. Le texte, les voix et
l'audio ne quittent pas le PC. Le modele XTTS est soumis a la Coqui Public Model
License et cette installation est reservee a l'usage personnel non commercial.

## Installation Windows actuelle

- environnement : `../xtts-lowkey/.venv` (Python 3.11)
- modele : cache Coqui local de Windows
- serveur : `services/xtts_server.py`
- voix francaise : `../chatterbox-lowkey/voices/Lowkey-FR-Valet.wav`
- voix anglaise : `../chatterbox-lowkey/voices/Henry.wav`

Le lanceur `lancer_jarvis.bat` demarre le serveur sans fenetre. Les empreintes
des deux voix sont calculees une seule fois au demarrage et gardees en memoire.
Chatterbox reste configure comme repli et ne demarre qu'en cas d'indisponibilite
de XTTS.

## Reinstallation

Creer un environnement Python 3.11 dans `../xtts-lowkey/.venv`, puis installer
PyTorch CUDA et `services/xtts-requirements.txt`. Au premier lancement, definir
`COQUI_TOS_AGREED=1` apres lecture et acceptation de la licence du modele.
