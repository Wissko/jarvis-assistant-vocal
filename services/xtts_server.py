"""Serveur XTTS v2 strictement local pour Lowkey.

Charge une seule fois le modele et les empreintes des deux voix, puis diffuse
du PCM WAV a mesure que XTTS le genere. Le serveur n'ecoute que 127.0.0.1.
"""
import os
import logging
import struct
import threading
from pathlib import Path

import truststore

truststore.inject_into_ssl()
os.environ.setdefault("COQUI_TOS_AGREED", "1")

RACINE = Path(__file__).resolve().parent.parent

# Verrou pris AVANT l'import de Torch et le chargement du modele. Sans lui, le
# lanceur et le provider pouvaient charger deux XTTS en parallele (~2 Go chacun).
_VERROU_PROCESSUS = None
if os.name == "nt":
    import msvcrt
    verrou_path = RACINE / "logs" / "xtts-process.lock"
    verrou_path.parent.mkdir(parents=True, exist_ok=True)
    _VERROU_PROCESSUS = open(verrou_path, "a+b")
    if verrou_path.stat().st_size == 0:
        _VERROU_PROCESSUS.write(b"0")
        _VERROU_PROCESSUS.flush()
    _VERROU_PROCESSUS.seek(0)
    try:
        msvcrt.locking(_VERROU_PROCESSUS.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("[XTTS] une autre instance est deja en cours.", flush=True)
        raise SystemExit(0)

import numpy as np
import torch
from flask import Flask, Response, jsonify, request, stream_with_context
from TTS.api import TTS

# La RTX 3060 prend en charge TF32 : les multiplications de matrices du GPT
# sont nettement plus rapides, sans convertir le modele ni doubler la VRAM.
if torch.cuda.is_available():
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.set_float32_matmul_precision("high")


ESPACE = RACINE.parent
VOIX = ESPACE / "chatterbox-lowkey" / "voices"
VOIX_FR = Path(os.environ.get("LOWKEY_XTTS_VOICE_FR", VOIX / "Lowkey-FR-Valet.wav"))
VOIX_EN = Path(os.environ.get("LOWKEY_XTTS_VOICE_EN", VOIX / "Henry.wav"))
PORT = int(os.environ.get("LOWKEY_XTTS_PORT", "8020"))
MODELE = "tts_models/multilingual/multi-dataset/xtts_v2"
FREQUENCE = 24000
TAILLE_FLUX = max(20, min(80, int(os.environ.get("LOWKEY_XTTS_STREAM_CHUNK", "40"))))

LOG_FILE = RACINE / "logs" / "xtts.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO, encoding="utf-8",
    format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("lowkey.xtts")

app = Flask(__name__)
verrou = threading.Lock()
device = "cuda" if torch.cuda.is_available() else "cpu"

print(f"[XTTS] chargement sur {device}...", flush=True)
api = TTS(MODELE, progress_bar=False).to(device)
modele = api.synthesizer.tts_model


def _empreinte(chemin):
    if not chemin.is_file():
        raise FileNotFoundError(f"reference vocale introuvable: {chemin}")
    with torch.inference_mode():
        return modele.get_conditioning_latents(audio_path=[str(chemin)])


empreintes = {"fr": _empreinte(VOIX_FR), "en": _empreinte(VOIX_EN)}
print("[XTTS] voix francaise et britannique prechargees.", flush=True)


def _entete_wav():
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI", b"RIFF", 0xFFFFFFFF, b"WAVE", b"fmt ", 16,
        1, 1, FREQUENCE, FREQUENCE * 2, 2, 16, b"data", 0xFFFFFFFF)


@app.get("/health")
def health():
    memoire = 0
    reservee = 0
    if torch.cuda.is_available():
        memoire = round(torch.cuda.memory_allocated() / 1024 ** 2)
        reservee = round(torch.cuda.memory_reserved() / 1024 ** 2)
    return jsonify({"ok": True, "loaded": True, "model": "XTTS v2",
                    "device": device, "vram_mb": memoire,
                    "vram_reserved_mb": reservee,
                    "stream_chunk_size": TAILLE_FLUX,
                    "voices": ["fr", "en"]})


@app.post("/stream")
def stream():
    donnees = request.get_json(silent=True) or {}
    texte = str(donnees.get("input") or donnees.get("text") or "").strip()
    langue = "en" if str(donnees.get("language") or "fr").lower().startswith("en") else "fr"
    vitesse = max(0.75, min(1.35, float(donnees.get("speed", 1.0))))
    if not texte:
        return jsonify({"error": "texte manquant"}), 400

    @stream_with_context
    def produire():
        latent, speaker = empreintes[langue]
        yield _entete_wav()
        with verrou, torch.inference_mode():
            morceaux = modele.inference_stream(
                texte, langue, latent, speaker,
                stream_chunk_size=TAILLE_FLUX, overlap_wav_len=1024,
                speed=vitesse, enable_text_splitting=True)
            dernier = None
            try:
                for morceau in morceaux:
                    audio = morceau.detach().float().cpu().numpy().reshape(-1)
                    audio = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
                    if dernier is not None:
                        yield dernier.tobytes()
                    dernier = audio
            except Exception:
                LOG.exception("inference interrompue (%s, %d caracteres)", langue, len(texte))
            finally:
                # Meme si XTTS rencontre une erreur, la sortie revient doucement
                # a zero au lieu de fermer brutalement le flux audio.
                if dernier is not None:
                    fondu = min(len(dernier), int(FREQUENCE * 0.18))
                    if fondu:
                        rampe = np.linspace(1.0, 0.0, fondu, dtype=np.float32)
                        dernier[-fondu:] = (
                            dernier[-fondu:].astype(np.float32) * rampe).astype("<i2")
                    yield dernier.tobytes()
                yield np.zeros(int(FREQUENCE * 0.12), dtype="<i2").tobytes()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

    return Response(produire(), mimetype="audio/wav",
                    headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, threaded=True, use_reloader=False)
