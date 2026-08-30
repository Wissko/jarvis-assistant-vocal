"""Lecture et écritures contrôlées dans TBS Workspace."""
from core import tbs
from core.registre import outil


@outil(
    nom="tbs_brief",
    description="Lit le CRM TBS et donne le brief business actuel: clients, projets, "
                "priorités, tâches, factures, abonnements et rendez-vous. À utiliser "
                "pour conseiller Yose sur son agence, son business ou sa journée.",
    lent=True,
    phrase_attente="Yose, j'analyse TBS Workspace.",
    affichage="toujours",
)
def tbs_brief() -> str:
    donnees, erreur = tbs.instantane(force=True)
    if not donnees:
        return f"TBS Workspace n'est pas accessible: {erreur}."
    suffixe = f" Données en cache, synchronisation impossible: {erreur}." if erreur else ""
    return tbs.formater(donnees) + suffixe


def _annonce_tache(args):
    projet = f" dans {args.get('projectName')}" if args.get("projectName") else ""
    return f"Je vais créer la tâche {args.get('name', '')}{projet} dans TBS Workspace."


@outil(
    nom="tbs_creer_tache",
    description="Crée une tâche dans TBS Workspace, éventuellement reliée à un projet. "
                "Utilise uniquement ce dépôt métier, pas les notes locales.",
    parametres={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nom clair et actionnable de la tâche."},
            "projectName": {"type": "string", "description": "Nom exact du projet TBS, optionnel."},
            "dueDate": {"type": "string", "description": "Échéance YYYY-MM-DD, optionnelle."},
            "priority": {"type": "string", "description": "Priorité, optionnelle."},
        },
        "required": ["name"],
    },
    confirmation=True,
    annonce=_annonce_tache,
)
def tbs_creer_tache(name: str, projectName: str = "", dueDate: str = "", priority: str = "") -> str:
    try:
        tbs.executer_action({
            "type": "create_task", "name": name, "projectName": projectName,
            "dueDate": dueDate, "priority": priority,
        })
        return f"La tâche {name} est enregistrée dans TBS Workspace."
    except RuntimeError as exc:
        return f"Je n'ai pas pu créer la tâche dans TBS: {exc}."


def _annonce_note(args):
    projet = f" dans {args.get('projectName')}" if args.get("projectName") else ""
    return f"Je vais ajouter la note {args.get('name', '')}{projet} dans TBS Workspace."


@outil(
    nom="tbs_ajouter_note",
    description="Ajoute une note métier dans TBS Workspace, éventuellement reliée à "
                "un projet. À utiliser pour les décisions, comptes rendus et informations business.",
    parametres={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Titre de la note."},
            "body": {"type": "string", "description": "Contenu de la note."},
            "projectName": {"type": "string", "description": "Nom exact du projet TBS, optionnel."},
        },
        "required": ["name", "body"],
    },
    confirmation=True,
    annonce=_annonce_note,
)
def tbs_ajouter_note(name: str, body: str, projectName: str = "") -> str:
    try:
        tbs.executer_action({
            "type": "create_note", "name": name, "body": body,
            "projectName": projectName,
        })
        return f"La note {name} est enregistrée dans TBS Workspace."
    except RuntimeError as exc:
        return f"Je n'ai pas pu ajouter la note dans TBS: {exc}."
