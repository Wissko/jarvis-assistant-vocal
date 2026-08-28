"""Detection locale d'une phrase d'activation a partir de blocs audio."""
from __future__ import annotations

from collections import deque
import re

import numpy as np

from core.util import sans_accents


def normaliser_activation(texte):
    texte = sans_accents((texte or "").lower())
    return " ".join(re.findall(r"[a-z0-9]+", texte))


def est_phrase_activation(texte, phrase="Lowkey"):
    """Tolere les graphies que Whisper produit pour la phrase franco-anglaise."""
    entendu = normaliser_activation(texte)
    cible = normaliser_activation(phrase)
    if cible and cible in entendu:
        return True
    lowkey = ("lowkey", "low key", "loki", "lo key", "loqui", "low ki")
    if cible in {"lowkey", "low key", "loki"}:
        return any(mot in entendu for mot in lowkey)
    protocole = ("protocole", "protocol", "protocoles")
    alpha = ("alpha", "alfa")
    return (any(mot in entendu for mot in lowkey)
            and any(mot in entendu for mot in protocole)
            and any(mot in entendu for mot in alpha))


class DetecteurActivationWhisper:
    """Accumule une courte phrase, puis la fait transcrire apres le silence."""

    def __init__(self, transcrire, phrase, seuil_parole, seuil_silence,
                 silence_fin=0.55, duree_max=4.5, taux=16000,
                 duree_parole_min=0.2):
        self.transcrire = transcrire
        self.phrase = phrase
        self.seuil_parole = float(seuil_parole)
        self.seuil_silence = float(seuil_silence)
        self.silence_fin = float(silence_fin)
        self.duree_max = float(duree_max)
        self.taux = int(taux)
        self.duree_parole_min = float(duree_parole_min)
        self._pre = deque(maxlen=3)
        self._audio = []
        self._actif = False
        self._silence = 0
        self._echantillons_paroles = 0
        self.derniere_transcription = ""
        self.nouvelle_transcription = False

    def reset(self):
        self._audio.clear()
        self._actif = False
        self._silence = 0
        self._echantillons_paroles = 0

    def ajouter(self, bloc):
        self.nouvelle_transcription = False
        bloc = np.asarray(bloc, dtype=np.float32).reshape(-1)
        niveau = float(np.sqrt(np.mean(bloc * bloc))) if bloc.size else 0.0
        if not self._actif:
            self._pre.append(bloc.copy())
            if niveau < self.seuil_parole:
                return False
            self._actif = True
            self._audio = list(self._pre)
            self._echantillons_paroles = bloc.size
            self._pre.clear()
            return False

        self._audio.append(bloc.copy())
        if niveau >= self.seuil_parole:
            self._echantillons_paroles += bloc.size
        self._silence = self._silence + bloc.size if niveau <= self.seuil_silence else 0
        duree = sum(x.size for x in self._audio) / self.taux
        fini = self._silence / self.taux >= self.silence_fin or duree >= self.duree_max
        if not fini:
            return False

        audio = np.concatenate(self._audio)
        assez_de_parole = self._echantillons_paroles / self.taux >= self.duree_parole_min
        self.reset()
        if not assez_de_parole:
            return False
        self.derniere_transcription = (self.transcrire(audio) or "").strip()
        self.nouvelle_transcription = True
        return est_phrase_activation(self.derniere_transcription, self.phrase)
