import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.codex_app_server import trouver_executable_codex


class TrouverExecutableCodexTests(unittest.TestCase):
    def test_conserve_une_commande_introuvable(self):
        with patch("core.codex_app_server.shutil.which", return_value=None):
            self.assertEqual(trouver_executable_codex("commande-absente"),
                             "commande-absente")

    def test_detecte_la_version_windows_la_plus_recente(self):
        with tempfile.TemporaryDirectory() as dossier:
            ancien = Path(dossier) / "OpenAI" / "Codex" / "bin" / "ancienne" / "codex.exe"
            recent = Path(dossier) / "OpenAI" / "Codex" / "bin" / "recente" / "codex.exe"
            ancien.parent.mkdir(parents=True)
            recent.parent.mkdir(parents=True)
            ancien.touch()
            recent.touch()
            os.utime(ancien, (1, 1))
            os.utime(recent, (2, 2))

            with (patch("core.codex_app_server.os.name", "nt"),
                  patch.dict(os.environ, {"LOCALAPPDATA": dossier}),
                  patch("core.codex_app_server.shutil.which", return_value=None)):
                self.assertEqual(Path(trouver_executable_codex("codex")),
                                 recent.resolve())


if __name__ == "__main__":
    unittest.main()
