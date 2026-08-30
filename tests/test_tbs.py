import unittest
from unittest.mock import patch

from core import tbs


class TbsContextTests(unittest.TestCase):
    def setUp(self):
        tbs._CACHE.update(at=0.0, data=None, error="")

    def test_contexte_statique_identifie_tbs_comme_source_de_verite(self):
        contexte = tbs.contexte_statique()
        self.assertIn("TBS Workspace est la source de vérité", contexte)
        self.assertIn("Howard CRM est un système séparé", contexte)
        self.assertIn("Loyalty Pass", contexte)

    def test_formate_un_brief_business_exploitable(self):
        contexte = tbs.formater({
            "metrics": {
                "clients": 2, "projects": 1, "openTasks": 3,
                "unpaidInvoices": 1, "activeSubscriptions": 1,
                "outstandingByCurrency": {"EUR": 1200},
                "monthlyRecurringByCurrency": {"EUR": 99},
            },
            "projects": [{"name": "Loyalty Pass", "status": "In progress"}],
            "openTasks": [{"name": "Relancer le client", "due_date": "2026-09-01"}],
            "unpaidInvoices": [{"name": "Facture 12", "amount": 1200, "currency": "EUR"}],
            "upcomingMeetings": [],
            "recentNotes": [],
        })
        self.assertIn("2 clients", contexte)
        self.assertIn("Loyalty Pass", contexte)
        self.assertIn("Relancer le client", contexte)
        self.assertIn("Facture 12", contexte)

    @patch("core.tbs.reglage")
    def test_degradation_propre_sans_configuration(self, reglage):
        reglage.side_effect = lambda chemin, defaut=None: defaut
        donnees, erreur = tbs.instantane(force=True)
        self.assertIsNone(donnees)
        self.assertIn("non configurée", erreur)


if __name__ == "__main__":
    unittest.main()
