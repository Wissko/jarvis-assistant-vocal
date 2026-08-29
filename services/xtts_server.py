"""Serveur XTTS v2 strictement local pour Lowkey.

Charge une seule fois le modele et les empreintes des deux voix, puis diffuse
du PCM WAV a mesure que XTTS le genere. Le serveur n'ecoute que 127.0.0.1.
"""
import os
import struct
import threading
from pathlib import Path

import truststore

truststore.inject_into_ssl()
os.environ.setdefault("COQUI_TOS_AGREED", "1")

import numpy as np
import torch
from flask import Flask, Response, jsonify, request, stream_with_context
from TTS.api import TTS


RACINE = Path(__file__).resolve().parent.parent
ESPACE = RACINE.parent
VOIX = ESPACE / "chatterbox-lowkey" / "voices"
VOIX_FR = Path(os.environ.get("LOWKEY_XTTS_VOICE_FR", VOIX / "Lowkey-FR-Valet.wav"))
VOIX_EN = Path(os.environ.get("LOWKEY_XTTS_VOICE_EN", VOIX / "Henry.wav"))
PORT = int(os.environ.get("LOWKEY_XTTS_PORT", "8020"))
MODELE = "tts_models/multilingual/multi-dataset/xtts_v2"
FREQUENCE = 24000

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
    if torch.cuda.is_available():
        memoire = round(torch.cuda.memory_allocated() / 1024 ** 2)
    return jsonify({"ok": True, "loaded": True, "model": "XTTS v2",
                    "device": device, "vram_mb": memoire,
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
                stream_chunk_size=20, overlap_wav_len=1024,
                speed=vitesse, enable_text_splitting=True)
            dernier = None
            for morceau in morceaux:
                audio = morceau.detach().float().cpu().numpy().reshape(-1)
                audio = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
                if dernier is not None:
                    yield dernier.tobytes()
                dernier = audio

            # Retient le dernier bloc pour terminer sur un fondu de 180 ms,
            # suivi d'un souffle nul tres court plutot que d'une coupure seche.
            if dernier is not None:
                fondu = min(len(dernier), int(FREQUENCE * 0.18))
                if fondu:
                    rampe = np.linspace(1.0, 0.0, fondu, dtype=np.float32)
                    dernier[-fondu:] = (dernier[-fondu:].astype(np.float32) * rampe).astype("<i2")
                yield dernier.tobytes()
                yield np.zeros(int(FREQUENCE * 0.12), dtype="<i2").tobytes()

    return Response(produire(), mimetype="audio/wav",
                    headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, threaded=True, use_reloader=False)
