import unittest

from core.tool_router import selectionner


SCHEMAS = [{"name": n} for n in (
    "remember", "recall", "forget", "allumer_lumiere", "changer_couleur",
    "lire_mails", "envoyer_mail", "browser_open", "chercher_web",
    "ouvrir_application", "eteindre_pc", "get_system_stats")]


class ToolRouterTests(unittest.TestCase):
    def noms(self, question):
        historique = [{"role": "user", "content": question}]
        return {x["name"] for x in selectionner(SCHEMAS, historique)}

    def test_selectionne_le_domaine_demande(self):
        noms = self.noms("Lowkey, allume la lumière du salon")
        self.assertIn("allumer_lumiere", noms)
        self.assertNotIn("envoyer_mail", noms)

    def test_question_generale_ne_transmet_que_la_memoire(self):
        self.assertEqual(self.noms("Pourquoi le ciel est bleu ?"),
                         {"remember", "recall", "forget"})

    def test_action_ambigue_conserve_tous_les_outils(self):
        self.assertEqual(len(self.noms("Fais-le maintenant")), len(SCHEMAS))


if __name__ == "__main__":
    unittest.main()
