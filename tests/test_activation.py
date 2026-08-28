import unittest

import numpy as np

from core.activation import DetecteurActivationWhisper, est_phrase_activation


class PhraseActivationTests(unittest.TestCase):
    def test_variantes_francaises_et_anglaises(self):
        for texte in ("Lowkey", "Low key", "Loki", "Lucky", "Looky"):
            with self.subTest(texte=texte):
                self.assertTrue(est_phrase_activation(texte))

    def test_refuse_une_phrase_partielle(self):
        self.assertFalse(est_phrase_activation("protocole alpha"))
        self.assertFalse(est_phrase_activation("okay lance Spotify"))

    def test_declenche_apres_la_fin_de_phrase(self):
        detecteur = DetecteurActivationWhisper(
            lambda audio: "Lowkey", "Lowkey",
            seuil_parole=0.02, seuil_silence=0.01, silence_fin=0.16)
        parole = np.full(1280, 0.1, dtype=np.float32)
        silence = np.zeros(1280, dtype=np.float32)
        self.assertFalse(detecteur.ajouter(parole))
        self.assertFalse(detecteur.ajouter(parole))
        self.assertFalse(detecteur.ajouter(parole))
        self.assertFalse(detecteur.ajouter(silence))
        self.assertTrue(detecteur.ajouter(silence))

    def test_ignore_un_clic_trop_court(self):
        detecteur = DetecteurActivationWhisper(
            lambda audio: "Lowkey", "Lowkey", seuil_parole=0.02,
            seuil_silence=0.01, silence_fin=0.16, duree_parole_min=0.2)
        clic = np.full(1280, 0.1, dtype=np.float32)
        silence = np.zeros(1280, dtype=np.float32)
        detecteur.ajouter(clic)
        detecteur.ajouter(silence)
        self.assertFalse(detecteur.ajouter(silence))


if __name__ == "__main__":
    unittest.main()
