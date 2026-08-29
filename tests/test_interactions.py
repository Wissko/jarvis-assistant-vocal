import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import interactions


class InteractionsTests(unittest.TestCase):
    def test_enregistre_et_relit_les_echanges(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "interactions.jsonl"
            with patch.object(interactions, "_FICHIER", fichier):
                interactions.ajouter("user", "Bonjour Lowkey", "fr")
                interactions.ajouter("assistant", "Bonsoir.", "fr")
                lus = interactions.lire(10)
        self.assertEqual([x["role"] for x in lus], ["user", "assistant"])
        self.assertEqual(lus[0]["texte"], "Bonjour Lowkey")

    def test_ignore_les_entrees_vides_ou_inconnues(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "interactions.jsonl"
            with patch.object(interactions, "_FICHIER", fichier):
                interactions.ajouter("outil", "secret")
                interactions.ajouter("user", "")
                self.assertEqual(interactions.lire(), [])


if __name__ == "__main__":
    unittest.main()
