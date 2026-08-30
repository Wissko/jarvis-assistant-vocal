"""Selection rapide des outils pertinents pour reduire la latence du LLM."""
import re

from core.util import sans_accents

_TOUJOURS = {"remember", "recall", "forget"}
_GROUPES = {
    "temps": ({"heure", "date", "meteo", "temps", "weather"}, {"heure_et_date", "meteo", "lancer_minuteur"}),
    "maison": ({"lumiere", "lampe", "salon", "chambre", "hue", "alexa", "google home", "amaran", "maison"}, {"allumer_lumiere", "regler_luminosite", "changer_couleur", "eteindre_tout", "alexa_etat", "alexa_annoncer", "alexa_routine", "alexa_appareil", "alexa_media", "google_home_etat", "google_home_allumer", "google_home_luminosite", "controler_amaran"}),
    "web": ({"web", "internet", "navigateur", "browser", "chrome", "site", "page", "onglet", "github", "recherche", "cherche", "ecran", "affiche"}, {"browser_open", "browser_current_page", "browser_tabs", "browser_close_tabs", "browser_interact", "chercher_web", "capture_screen", "cliquer_ecran"}),
    "applications": ({"ouvre", "ouvrir", "lance", "application", "logiciel", "app"}, {"launch_app", "ajouter_app", "ouvrir_application", "ouvrir_panneau"}),
    "audio": ({"musique", "chanson", "spotify", "playlist", "volume", "son", "casque", "enceinte", "media"}, {"identifier_musique", "identifier_musique_fichier", "derniere_musique", "ajouter_a_playlist", "controler_media", "regler_volume", "sortie_audio"}),
    "agenda": ({"agenda", "calendrier", "rendez-vous", "rendez vous", "evenement", "deadline", "planning"}, {"get_events", "create_event", "delete_event", "get_deadlines", "book_appointment", "confirmer_reservation"}),
    "mail": ({"mail", "email", "courriel"}, {"lire_mails", "lire_mail", "preparer_mail", "envoyer_mail", "mettre_a_la_corbeille"}),
    "notes": ({"note", "idee", "memo", "souviens", "rappelle"}, {"sortir_idee", "notes_du_jour", "noter", "nouvelle_idee_video", "remember", "recall", "forget"}),
    "contenu": ({"contenu", "video", "script", "youtube", "inspiration", "tiktok"}, {"chercher_inspiration", "generer_idees_contenu", "generer_script", "lancer_ingestion_youtube", "nouvelle_idee_video", "changer_statut_contenu", "ou_j_en_suis", "etat_contenus"}),
    "finance": ({"finance", "budget", "banque", "releve", "abonnement", "transaction"}, {"mon_budget", "importer_releve", "corriger_categorie", "detecter_abonnements", "integrer_abonnements_detectes", "cout_appels"}),
    "business": ({"tbs", "business", "agence", "client", "projet", "priorite", "facture", "crm", "workspace", "chiffre", "vente", "commercial"}, {"tbs_brief", "tbs_creer_tache", "tbs_ajouter_note"}),
    "stream": ({"obs", "stream", "record", "enregistre", "scene", "replay"}, {"start_stream", "stop_stream", "start_record", "stop_record", "switch_scene", "save_replay"}),
    "communication": ({"appel", "telephone", "discord", "instagram", "mention"}, {"call_and_book", "call_with_message", "cout_appels", "get_mentions_summary", "get_channel_summary", "instagram_resume", "rafraichir_instagram"}),
    "systeme": ({"pc", "ordinateur", "systeme", "cpu", "gpu", "ram", "eteins", "arrete", "presence", "geste", "personnalite", "mode"}, {"get_system_stats", "eteindre_pc", "annuler_extinction", "detection_presence", "controler_gestes", "changer_personnalite", "mode_routage", "activer_mode", "afficher_reponses", "afficher_reponse", "mode_silencieux_visuel", "reglage_overlay"}),
}
_ACTION_AMBIGUE = re.compile(r"\b(fais|fait|mets|met|active|desactive|execute|demarre|lance|ouvre|ferme|cree|ajoute|supprime|envoie|appelle|change|regle)\b")


def derniere_question(historique):
    for message in reversed(historique or []):
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            return message["content"]
    return ""


def selectionner(schemas, historique, actif=True):
    """Retourne un petit catalogue pertinent; conserve tout si l'action est ambigue."""
    schemas = list(schemas or [])
    if not actif or not schemas:
        return schemas
    question = sans_accents(derniere_question(historique).lower())
    noms, correspondance = set(_TOUJOURS), False
    for mots, outils in _GROUPES.values():
        if any(sans_accents(mot) in question for mot in mots):
            noms.update(outils)
            correspondance = True
    if not correspondance and _ACTION_AMBIGUE.search(question):
        return schemas
    selection = [schema for schema in schemas if schema.get("name") in noms]
    return selection or schemas
