import io
import json
import struct
import unittest
from unittest.mock import patch

from core.tts import (ChatterboxProvider, ElevenLabsProvider, XTTSProvider,
                      parametres_voix_windows, reinitialiser, tts)
from core.voix import texte_a_prononcer


class VoixBilingueTests(unittest.TestCase):
    def test_yose_est_ecrit_yose_et_prononce_yosser(self):
        self.assertEqual(
            texte_a_prononcer("Yose, c'est fait.", "Yose", "Yosser"),
            "Yosser, c'est fait.")
        self.assertEqual(
            texte_a_prononcer("Bonjour YOSE.", "Yose", "Yosser"),
            "Bonjour Yosser.")

    def test_voix_masculines_par_defaut(self):
        with patch("core.tts.reglage", side_effect=lambda chemin, defaut=None: defaut):
            self.assertEqual(parametres_voix_windows("fr-FR")[:2],
                             ("fr", "Microsoft Paul"))
            self.assertEqual(parametres_voix_windows("en-US")[:2],
                             ("en", "Microsoft Mark"))

    def test_style_est_borne(self):
        valeurs = {"voix_windows.debit": 99, "voix_windows.volume": 999}
        with patch("core.tts.reglage",
                   side_effect=lambda chemin, defaut=None: valeurs.get(chemin, defaut)):
            self.assertEqual(parametres_voix_windows("fr")[2:], (10, 100))

    def test_sans_cle_elevenlabs_revient_immediatement_a_windows(self):
        with patch("core.tts.reglage", return_value=""):
            fournisseur = ElevenLabsProvider()
        with patch("core.tts.urllib.request.urlopen",
                   side_effect=AssertionError("aucun appel reseau attendu")):
            self.assertIsNone(fournisseur.synthetiser("Bonjour", langue="fr"))

    def test_chatterbox_emploie_la_bonne_voix_bilingue(self):
        valeurs = {
            "chatterbox.actif": True,
            "chatterbox.voix_fr": "Lowkey-FR.wav",
            "chatterbox.voix_en": "Lowkey-UK.wav",
        }
        with patch("core.tts.reglage",
                   side_effect=lambda chemin, defaut=None: valeurs.get(chemin, defaut)):
            fournisseur = ChatterboxProvider()
        self.assertEqual(fournisseur._parametres("fr-FR"), ("Lowkey-FR.wav", "fr"))
        self.assertEqual(fournisseur._parametres("en-GB"), ("Lowkey-UK.wav", "en"))

    def test_chatterbox_diffuse_le_pcm_par_petits_morceaux(self):
        valeurs = {
            "chatterbox.actif": True,
            "chatterbox.voix_fr": "Lowkey-FR.wav",
            "chatterbox.taille_flux": 50,
        }
        with patch("core.tts.reglage",
                   side_effect=lambda chemin, defaut=None: valeurs.get(chemin, defaut)):
            fournisseur = ChatterboxProvider()

        entete = bytearray(44)
        entete[:4], entete[8:12] = b"RIFF", b"WAVE"
        entete[24:28] = struct.pack("<I", 24000)
        reponse = io.BytesIO(bytes(entete) + struct.pack("<4h", 1, -2, 3, -4))
        appels = []

        def ouvrir(requete, timeout=None):
            appels.append(json.loads(requete.data.decode("utf-8")))
            return reponse

        with patch.object(fournisseur, "_demarrer_si_necessaire", return_value=True), \
             patch("core.tts.urllib.request.urlopen", side_effect=ouvrir):
            morceaux, frequence = fournisseur.synthetiser_en_flux("Bonjour", "fr")
            self.assertEqual(frequence, 24000)
            self.assertEqual(next(morceaux).tolist(), [1, -2, 3, -4])

        self.assertTrue(appels[0]["stream"])
        self.assertEqual(appels[0]["chunk_size"], 50)
        self.assertEqual(appels[0]["predefined_voice_id"], "Lowkey-FR.wav")

    def test_xtts_est_prioritaire_sur_chatterbox(self):
        valeurs = {"xtts.actif": True, "chatterbox.actif": True}
        reinitialiser()
        try:
            with patch("core.tts.reglage",
                       side_effect=lambda chemin, defaut=None: valeurs.get(chemin, defaut)), \
                 patch("core.routage.mode_actuel", return_value="hybride"):
                self.assertIsInstance(tts(), XTTSProvider)
        finally:
            reinitialiser()


if __name__ == "__main__":
    unittest.main()
