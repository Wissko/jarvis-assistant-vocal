"""Outil vocal : activer / couper le contrôle par gestes de la main (webcam).

Le tracking tourne dans un sous-process isolé (Python 3.11 + MediaPipe) ; voir
core/gestes.py et docs/gestes.md. mcp_expose=False : la caméra n'est JAMAIS pilotable
à distance (ni MCP, ni Hermes).
"""
from core.registre import outil


@outil(
    nom="controler_gestes",
    description="Active ou coupe le contrôle par gestes de la main (webcam). A utiliser "
                "pour 'active les gestes', 'coupe les gestes', 'allume/éteins la caméra "
                "des gestes', 'Jarvis regarde mes mains'.",
    parametres={
        "type": "object",
        "properties": {
            "actif": {"type": "boolean", "description": "true = activer, false = couper."}
        },
        "required": ["actif"],
    },
)
def controler_gestes(actif: bool) -> str:
    from core import gestes
    return gestes.demarrer() if actif else gestes.arreter()
