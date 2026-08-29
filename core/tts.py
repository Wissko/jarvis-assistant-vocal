"""Abstraction de la synthese vocale (TTS) : cloud ou local, meme interface.

Chaque provider expose `synthetiser(texte, langue)` qui renvoie (audio_int16, frequence)
ou None. jarvis14 se charge de JOUER l'audio (avec sa gestion d'interruption) et
retombe sur la voix Windows (SAPI) si le provider renvoie None.

  - ChatterboxProvider : local, voix humaine bilingue via le serveur Chatterbox.
  - ElevenLabsProvider : cloud (qualite max), voix configurable.
  - PiperProvider      : local, 100% offline, voix francaise Piper (.onnx).

Choix par config.yaml (mode: cloud | local). En local sans modele Piper, ou en
cloud sans cle ElevenLabs, on retombe proprement sur SAPI.

Note honnete sur le TTS local francais : Piper est recommande (voix FR eprouvees
comme fr_FR-siwis / fr_FR-tom, tres leger, temps reel sur CPU). Kokoro (kokoro-onnx)
ne propose qu'une voix FR recente et de qualite moyenne ; Piper est un meilleur
choix pour le francais aujourd'hui.
"""
import json
import logging
import os
import struct
import subprocess
import time
import urllib.request
from pathlib import Path

# Magasin de certificats Windows (Malwarebytes intercepte le TLS : sans ca, l'appel
# a l'API ElevenLabs echoue et Jarvis retombe sur la voix Windows).
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from core.config import reglage

LOG = logging.getLogger("jarvis")
_RACINE = Path(__file__).resolve().parent.parent


def parametres_voix_windows(langue=None):
    """Voix SAPI masculine et style a employer pour la langue courante."""
    code = "en" if str(langue or "").lower().startswith("en") else "fr"
    nom = reglage(
        f"voix_windows.{code}", "Microsoft Mark" if code == "en" else "Microsoft Paul")
    debit = max(-10, min(10, int(reglage("voix_windows.debit", -1))))
    volume = max(0, min(100, int(reglage("voix_windows.volume", 100))))
    return code, str(nom or ""), debit, volume


class ProviderTTS:
    nom = "?"

    def disponible(self):
        return True

    def synthetiser(self, texte, langue=None):
        """Renvoie (numpy int16 mono, frequence_hz) ou None si indisponible."""
        return None

    def synthetiser_en_flux(self, texte, langue=None):
        """Renvoie (iterateur_audio_int16, frequence_hz), si le provider sait diffuser."""
        return None


# --------------------------------------------------------------- XTTS v2

class XTTSProvider(ProviderTTS):
    """Voix bilingue clonee, locale et diffusee par XTTS v2."""

    nom = "XTTS v2"
    _processus = None

    def __init__(self):
        self.actif = bool(reglage("xtts.actif", False))
        self.hote = str(reglage("xtts.hote", "http://127.0.0.1:8020")).rstrip("/")
        self.vitesse = float(reglage("xtts.vitesse", 1.0))
        self.timeout = float(reglage("xtts.timeout", 180))
        self.demarrage_auto = bool(reglage("xtts.demarrage_auto", True))
        dossier = Path(str(reglage("xtts.dossier", "../xtts-lowkey")))
        self.dossier = dossier if dossier.is_absolute() else (_RACINE / dossier).resolve()
        self.repli = ChatterboxProvider()

    def disponible(self):
        return self.actif

    def _serveur_repond(self):
        try:
            with urllib.request.urlopen(f"{self.hote}/health", timeout=1.5) as reponse:
                return bool(json.loads(reponse.read()).get("loaded"))
        except Exception:
            return False

    def _demarrer_si_necessaire(self):
        if self._serveur_repond():
            return True
        if not self.demarrage_auto:
            return False
        python = self.dossier / ".venv" / "Scripts" / "python.exe"
        serveur = _RACINE / "services" / "xtts_server.py"
        if not python.exists() or not serveur.exists():
            LOG.warning("XTTS v2 non installe dans %s", self.dossier)
            return False
        try:
            options = {"cwd": str(_RACINE), "stdout": subprocess.DEVNULL,
                       "stderr": subprocess.DEVNULL,
                       "env": {**os.environ, "COQUI_TOS_AGREED": "1"}}
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NO_WINDOW
            type(self)._processus = subprocess.Popen(
                [str(python), str(serveur)], **options)
            limite = time.monotonic() + self.timeout
            while time.monotonic() < limite:
                if self._serveur_repond():
                    return True
                if type(self)._processus.poll() is not None:
                    break
                time.sleep(1)
        except Exception as e:
            LOG.warning("demarrage XTTS impossible: %s", e)
        return False

    def synthetiser_en_flux(self, texte, langue=None):
        if not self.disponible() or not self._demarrer_si_necessaire():
            return self.repli.synthetiser_en_flux(texte, langue)
        try:
            import numpy as np
            code = "en" if str(langue or "").lower().startswith("en") else "fr"
            charge = {"input": texte, "language": code, "speed": self.vitesse}
            requete = urllib.request.Request(
                f"{self.hote}/stream", data=json.dumps(charge).encode("utf-8"),
                method="POST", headers={"Content-Type": "application/json",
                                        "Accept": "audio/wav"})
            reponse = urllib.request.urlopen(requete, timeout=self.timeout)
            entete = reponse.read(44)
            if len(entete) != 44 or entete[:4] != b"RIFF" or entete[8:12] != b"WAVE":
                reponse.close()
                raise ValueError("flux WAV XTTS invalide")
            frequence = struct.unpack("<I", entete[24:28])[0]

            def morceaux():
                reste = b""
                try:
                    while True:
                        lire = getattr(reponse, "read1", reponse.read)
                        bloc = lire(8192)
                        if not bloc:
                            break
                        bloc = reste + bloc
                        limite = len(bloc) - len(bloc) % 2
                        if limite:
                            yield np.frombuffer(bloc[:limite], dtype="<i2").copy()
                        reste = bloc[limite:]
                finally:
                    reponse.close()

            return morceaux(), frequence
        except Exception as e:
            LOG.warning("flux XTTS indisponible, repli Chatterbox: %s", e)
            return self.repli.synthetiser_en_flux(texte, langue)

    def synthetiser(self, texte, langue=None):
        flux = self.synthetiser_en_flux(texte, langue)
        if flux is None:
            return None
        morceaux, frequence = flux
        try:
            import numpy as np
            return np.concatenate(list(morceaux)), frequence
        except Exception:
            return None


# --------------------------------------------------------------- Chatterbox

class ChatterboxProvider(ProviderTTS):
    """Voix locale naturelle fournie par Chatterbox-TTS-Server."""

    nom = "Chatterbox"
    _processus = None

    def __init__(self):
        self.actif = bool(reglage("chatterbox.actif", False))
        self.hote = str(reglage("chatterbox.hote", "http://127.0.0.1:8004")).rstrip("/")
        self.voix_fr = str(reglage("chatterbox.voix_fr", "Lowkey-FR-Valet.wav"))
        self.voix_en = str(reglage("chatterbox.voix_en", "Henry.wav"))
        self.vitesse = float(reglage("chatterbox.vitesse", 1.08))
        self.seed = int(reglage("chatterbox.seed", 108))
        self.taille_flux = max(50, min(500, int(
            reglage("chatterbox.taille_flux", 50))))
        self.timeout = float(reglage("chatterbox.timeout", 120))
        self.demarrage_auto = bool(reglage("chatterbox.demarrage_auto", True))
        dossier = reglage("chatterbox.dossier", "../chatterbox-lowkey")
        p = Path(str(dossier))
        self.dossier = p if p.is_absolute() else (_RACINE / p).resolve()

    def disponible(self):
        return self.actif

    def _parametres(self, langue=None):
        anglais = str(langue or "").lower().startswith("en")
        return (self.voix_en if anglais else self.voix_fr,
                "en" if anglais else "fr")

    def _serveur_repond(self):
        try:
            with urllib.request.urlopen(f"{self.hote}/v1/audio/voices", timeout=1.5):
                return True
        except Exception:
            return False

    def _demarrer_si_necessaire(self):
        if self._serveur_repond():
            return True
        if not self.demarrage_auto:
            return False
        python = self.dossier / "python_embedded" / "python.exe"
        serveur = self.dossier / "server.py"
        if not python.exists() or not serveur.exists():
            LOG.warning("Chatterbox non installe dans %s", self.dossier)
            return False
        try:
            options = {"cwd": str(self.dossier), "stdout": subprocess.DEVNULL,
                       "stderr": subprocess.DEVNULL}
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NO_WINDOW
            type(self)._processus = subprocess.Popen(
                [str(python), str(serveur)], **options)
            limite = time.monotonic() + self.timeout
            while time.monotonic() < limite:
                if self._serveur_repond():
                    return True
                if type(self)._processus.poll() is not None:
                    break
                time.sleep(1)
        except Exception as e:
            LOG.warning("demarrage Chatterbox impossible: %s", e)
        return False

    def synthetiser(self, texte, langue=None):
        if not self.disponible() or not self._demarrer_si_necessaire():
            return None
        try:
            import miniaudio
            import numpy as np
            voix, code = self._parametres(langue)
            charge = {
                "model": "chatterbox-multilingual",
                "input": texte,
                "voice": voix,
                "response_format": "wav",
                "speed": self.vitesse,
                "seed": self.seed,
                "language": code,
            }
            requete = urllib.request.Request(
                f"{self.hote}/v1/audio/speech",
                data=json.dumps(charge).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json", "Accept": "audio/wav"})
            with urllib.request.urlopen(requete, timeout=self.timeout) as reponse:
                wav = reponse.read()
            decode = miniaudio.decode(
                wav, nchannels=1, sample_rate=24000,
                output_format=miniaudio.SampleFormat.SIGNED16)
            return np.frombuffer(decode.samples, dtype=np.int16), 24000
        except Exception as e:
            print(f"  [Chatterbox] indisponible ({e}), repli voix Windows.")
            return None

    def synthetiser_en_flux(self, texte, langue=None):
        """Diffuse le PCM des qu'un premier morceau Chatterbox est disponible.

        Le serveur produit toujours chaque morceau en une passe, mais Lowkey n'attend
        plus la generation de toute la reponse avant de commencer la lecture.
        """
        if not self.disponible() or not self._demarrer_si_necessaire():
            return None
        try:
            import numpy as np
            voix, code = self._parametres(langue)
            charge = {
                "text": texte,
                "voice_mode": "predefined",
                "predefined_voice_id": voix,
                "output_format": "wav",
                "split_text": True,
                "chunk_size": self.taille_flux,
                "speed_factor": self.vitesse,
                "seed": self.seed,
                "language": code,
                "stream": True,
            }
            requete = urllib.request.Request(
                f"{self.hote}/tts",
                data=json.dumps(charge).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json", "Accept": "audio/wav"})
            reponse = urllib.request.urlopen(requete, timeout=self.timeout)

            # Le WAV diffuse a une taille inconnue, mais son en-tete PCM reste standard.
            entete = reponse.read(44)
            if len(entete) != 44 or entete[:4] != b"RIFF" or entete[8:12] != b"WAVE":
                reponse.close()
                raise ValueError("flux WAV Chatterbox invalide")
            frequence = struct.unpack("<I", entete[24:28])[0]

            def morceaux():
                reste = b""
                try:
                    while True:
                        lire = getattr(reponse, "read1", reponse.read)
                        bloc = lire(8192)
                        if not bloc:
                            break
                        bloc = reste + bloc
                        limite = len(bloc) - (len(bloc) % 2)
                        if limite:
                            # Copie necessaire : le tampon HTTP est reutilise ensuite.
                            yield np.frombuffer(bloc[:limite], dtype="<i2").copy()
                        reste = bloc[limite:]
                finally:
                    reponse.close()

            return morceaux(), frequence
        except Exception as e:
            LOG.warning("flux Chatterbox indisponible: %s", e)
            return None


# --------------------------------------------------------------- ElevenLabs

class ElevenLabsProvider(ProviderTTS):
    nom = "ElevenLabs"

    def __init__(self):
        self.cle = reglage("elevenlabs.cle", "")
        self.voix = reglage("elevenlabs.voix", "")
        self.modele = reglage("elevenlabs.modele", "eleven_flash_v2_5")
        self._voix_resolue = None

    def disponible(self):
        return bool(self.cle)

    def _resoudre_voix(self):
        if self.voix:
            return self.voix
        if self._voix_resolue:
            return self._voix_resolue
        try:
            requete = urllib.request.Request(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": self.cle})
            with urllib.request.urlopen(requete, timeout=6) as reponse:
                d = json.loads(reponse.read().decode("utf-8"))
            self._voix_resolue = d["voices"][0]["voice_id"]
        except Exception:
            self._voix_resolue = "21m00Tcm4TlvDq8ikWAM"   # Rachel, par defaut
        return self._voix_resolue

    def synthetiser(self, texte, langue=None):
        if not self.disponible():
            return None
        try:
            import miniaudio
            import numpy as np
        except ImportError:
            return None
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self._resoudre_voix()}"
        charge = {"text": texte, "model_id": self.modele}
        # Flash/Turbo v2.5 acceptent language_code : on propage la langue detectee
        # par Whisper pour conserver la bonne prononciation en francais/anglais.
        if any(x in self.modele for x in ("flash", "turbo")):
            configuree = reglage("elevenlabs.langue", "auto")
            code = langue if configuree in (None, "", "auto") else configuree
            if code:
                charge["language_code"] = str(code).split("-")[0].lower()
        corps = json.dumps(charge).encode("utf-8")
        requete = urllib.request.Request(url, data=corps, method="POST", headers={
            "xi-api-key": self.cle, "Content-Type": "application/json",
            "Accept": "audio/mpeg"})
        try:
            with urllib.request.urlopen(requete, timeout=15) as reponse:
                mp3 = reponse.read()
            decode = miniaudio.decode(
                mp3, nchannels=1, sample_rate=24000,
                output_format=miniaudio.SampleFormat.SIGNED16)
            try:                                  # N12 : comptabilite voix (au caractere)
                from core import budget
                budget.enregistrer_tts(len(texte or ""))
            except Exception:
                pass
            return np.frombuffer(decode.samples, dtype=np.int16), 24000
        except Exception as e:
            print(f"  [ElevenLabs] indisponible ({e}), repli voix Windows.")
            return None


# --------------------------------------------------------------- Piper (local)

class PiperProvider(ProviderTTS):
    nom = "Piper"

    def __init__(self):
        self.modele = reglage("piper.modele", "")
        self._voix = None

    def _chemin(self):
        if not self.modele:
            # a defaut, prend le premier .onnx trouve dans voix/
            trouves = list((_RACINE / "voix").glob("*.onnx"))
            return trouves[0] if trouves else None
        p = Path(self.modele)
        return p if p.is_absolute() else (_RACINE / p)

    def disponible(self):
        c = self._chemin()
        return bool(c and c.exists())

    def synthetiser(self, texte, langue=None):
        try:
            import numpy as np
            from piper import PiperVoice
        except ImportError:
            print("  [Piper] librairie piper-tts absente.")
            return None
        chemin = self._chemin()
        if chemin is None or not chemin.exists():
            print("  [Piper] aucun modele de voix (.onnx) dans voix/. Voir docs.")
            return None
        try:
            if self._voix is None:
                self._voix = PiperVoice.load(str(chemin))

            # Ancienne API (piper-tts <= 1.2.x) : synthesize_stream_raw() -> PCM brut.
            if hasattr(self._voix, "synthesize_stream_raw"):
                brut = b"".join(self._voix.synthesize_stream_raw(texte))
                return np.frombuffer(brut, dtype=np.int16), self._voix.config.sample_rate

            # Nouvelle API (piper-tts >= 1.3.0, réécriture OHF-Voice/piper1-gpl) :
            # synthesize() renvoie des AudioChunk (int16 + sample_rate). C'est le
            # cas de la version par défaut de requirements.txt (issue NOVON82).
            morceaux, freq = [], None
            for chunk in self._voix.synthesize(texte):
                octets = getattr(chunk, "audio_int16_bytes", None)
                if octets is None:                       # repli : tableau float
                    arr = getattr(chunk, "audio_float_array", None)
                    if arr is not None:
                        octets = (np.asarray(arr) * 32767).astype(np.int16).tobytes()
                if octets:
                    morceaux.append(octets)
                if freq is None:
                    freq = getattr(chunk, "sample_rate", None)
            brut = b"".join(morceaux)
            if not brut:
                return None
            if not freq:
                freq = getattr(getattr(self._voix, "config", None), "sample_rate", 22050)
            return np.frombuffer(brut, dtype=np.int16), freq
        except Exception as e:
            print(f"  [Piper] echec ({e}), repli voix Windows.")
            return None


# --------------------------------------------------------------- Kokoro (local)

class KokoroProvider(ProviderTTS):
    nom = "Kokoro"

    def __init__(self):
        self.modele = reglage("kokoro.modele", "")
        self.voix = reglage("kokoro.voix", "")
        self.voix_nom = reglage("kokoro.voix_nom", "ff_siwis")
        self._k = None

    def disponible(self):
        return bool(self.modele and Path(self.modele).exists())

    def synthetiser(self, texte, langue=None):
        try:
            import numpy as np
            from kokoro_onnx import Kokoro
        except ImportError:
            print("  [Kokoro] librairie absente. Installe : uv add kokoro-onnx")
            return None
        if not (self.modele and Path(self.modele).exists()):
            print("  [Kokoro] modele introuvable (kokoro.modele). Voir docs/local.md.")
            return None
        try:
            if self._k is None:
                self._k = Kokoro(self.modele, self.voix)
            code = "en-us" if str(langue or "").lower().startswith("en") else "fr-fr"
            samples, freq = self._k.create(
                texte, voice=self.voix_nom, speed=1.0, lang=code)
            audio = (np.asarray(samples) * 32767).astype(np.int16)
            return audio, freq
        except Exception as e:
            print(f"  [Kokoro] echec ({e}), repli voix Windows.")
            return None


# --------------------------------------------------------------- fabrique

_TTS = None


def tts():
    """Provider TTS courant, XTTS puis Chatterbox quand ils sont actifs."""
    global _TTS
    if _TTS is None:
        from core.routage import mode_actuel
        m = mode_actuel()
        if reglage("xtts.actif", False):
            _TTS = XTTSProvider()
        elif reglage("chatterbox.actif", False):
            _TTS = ChatterboxProvider()
        elif m == "local":
            moteur = (reglage("voix_locale", "piper") or "piper").lower()
            _TTS = KokoroProvider() if moteur == "kokoro" else PiperProvider()
        else:
            _TTS = ElevenLabsProvider()
        LOG.info("provider TTS : %s (mode %s)", _TTS.nom, m)
    return _TTS


def reinitialiser():
    """Force la reconstruction du provider TTS au prochain tts() (switch de mode)."""
    global _TTS
    _TTS = None
