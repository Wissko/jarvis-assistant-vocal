import unittest
from unittest.mock import patch

from core.tts import ElevenLabsProvider, parametres_voix_windows


class VoixBilingueTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
