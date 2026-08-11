"""Outils de contenu : recherche d'inspiration (Jarvis) + generation (deleguee a Hermes).

Doctrine : Jarvis = interface vocale rapide ; Hermes = moteur d'analyse/generation.
Hermes lit le Vault + le projet Scripts en LECTURE SEULE dans son conteneur Docker
(cf. HERMES_NOTES.md §17) ; il n'ecrit que dans drafts/.
"""
from core import hub_contenu
from core.registre import outil
from tools.deleguer_a_hermes import deleguer_en_fond


@outil(
    nom="chercher_inspiration",
    mcp_expose=True,
    description=(
        "Cherche dans le vault d'inspirations (videos Insta/TikTok sauvegardees) sur un "
        "sujet : titres, themes, tags, resumes et transcriptions. Repond COURT a la voix "
        "et laisse le detail dans la conversation. Ex: 'cherche mes inspirations sur les hooks'."),
    parametres={"type": "object", "properties": {
        "sujet": {"type": "string", "description": "Le sujet ou mot-cle a chercher."}},
        "required": ["sujet"]},
)
def chercher_inspiration(sujet):
    """Recherche ponderee dans le Vault (cote Jarvis, rapide)."""
    resultats = hub_contenu.chercher(sujet, n=6)
    if not resultats:
        return f"Rien trouve sur « {sujet} » dans le vault."
    lignes = [f"- {e['titre']} — {e['auteur']} [{', '.join(e['themes'])}]\n  {e['lien']}"
              for e in resultats]
    return (f"{len(resultats)} inspiration(s) sur « {sujet} » "
            f"(annonce-en UNE a la voix, garde le detail ici) :\n" + "\n".join(lignes))


@outil(
    nom="generer_idees_contenu",
    mcp_expose=True,
    description=(
        "Genere des idees de contenu en DELEGUANT a Hermes l'analyse du vault (tendances, "
        "formats, hooks recurrents) puis la proposition de concepts. Jarvis repond tout de "
        "suite et annonce le resultat a voix haute quand c'est pret. Ex: 'genere-moi des idees'."),
)
def generer_idees_contenu():
    """Delegue l'analyse du vault + 5 concepts a Hermes ; notif vocale differee."""
    tache = (
        "Tu as acces en LECTURE au dossier /vault (mes inspirations video Insta/TikTok : "
        "/vault/index.md + fiches /vault/raw/*.md avec front-matter themes/tags/format et "
        "transcriptions). Analyse-le : degage les tendances, les formats qui reviennent et "
        "les hooks recurrents, puis propose 5 CONCEPTS de contenu concrets et originaux, "
        "adaptes a ce que je sauvegarde. Termine par une ligne commencant par 'RESUME:' de "
        "2 phrases maximum pour une lecture a voix haute.")
    return deleguer_en_fond(tache, intro="Hermes a des idees. ", nom_thread="idees-contenu")


@outil(
    nom="generer_script",
    confirmation=True,
    description=(
        "Ecrit un brouillon de script video en DELEGUANT a Hermes (skill maison : "
        "corrections.md en autorite max, ma fiche de style, mes scripts existants). Le "
        "brouillon atterrit dans drafts/. Confirmation requise. Ex: 'ecris un script sur X'."),
    parametres={"type": "object", "properties": {
        "sujet": {"type": "string", "description": "Le sujet du script."},
        "style": {"type": "string", "description": "Createur/style de reference (optionnel)."}},
        "required": ["sujet"]},
    annonce=lambda a: f"Je vais demander a Hermes un brouillon de script sur : {a.get('sujet', '')}.",
)
def generer_script(sujet, style=""):
    """Delegue la redaction a Hermes (skill generer_script_maison) ; sortie dans drafts/."""
    contrainte = f" Style de reference : {style}." if style else ""
    tache = (
        f"Ecris un brouillon de SCRIPT VIDEO sur : {sujet}.{contrainte}\n\n"
        "Tu as acces en LECTURE a /scripts (mon projet d'ecriture). HIERARCHIE STRICTE, en "
        "cas de contradiction : 1) /scripts/corrections.md = AUTORITE MAXIMALE (ne reproduis "
        "JAMAIS une formulation que j'y ai corrigee) ; 2) /scripts/sources/clean/moi/*.md = "
        "mes scripts reels ; 3) /scripts/styles/moi.md = ma fiche de style ; "
        "4) /scripts/styles/<createur>.md pour la structure et le rythme SEULEMENT. Ecris "
        "DANS MA VOIX, jamais celle des createurs de reference. Angle et plan d'abord dans ta "
        "reflexion, puis redaction. Ecris le brouillon final dans un fichier "
        "/scripts/drafts/<nom-court>.md (tu n'as le droit d'ecrire QUE dans drafts/). "
        "Termine par une ligne 'RESUME:' donnant le nom du fichier cree et l'angle choisi, "
        "en 2 phrases, pour la voix.")
    return deleguer_en_fond(tache, intro="Ton brouillon est pret. ", nom_thread="generer-script")
