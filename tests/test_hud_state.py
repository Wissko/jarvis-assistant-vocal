import unittest

import hud


class HudStateTests(unittest.TestCase):
    def test_instantane_expose_etat_vocal_et_derniere_interaction(self):
        hud.etat("ecoute")
        hud.niveau(0.42)
        hud.dire_vous("Bonjour Lowkey")
        etat = hud.instantane()
        self.assertEqual(etat["etat"], "ecoute")
        self.assertAlmostEqual(etat["niveau"], 0.42)
        self.assertEqual(etat["dernier"]["t"], "vous")


if __name__ == "__main__":
    unittest.main()
