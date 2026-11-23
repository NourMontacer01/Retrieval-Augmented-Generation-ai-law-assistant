"""Tous les chemins du projet, a un seul endroit.

Les chemins partent de la racine du projet (le dossier qui contient conformite/) :
les commandes marchent donc quel que soit le dossier depuis lequel on les lance.
"""
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

FICHIER_SOURCES = RACINE / "config" / "sources.json"
FICHIER_ENV = RACINE / ".env"

DOSSIER_BRUT = RACINE / "data" / "brut"
FICHIER_MORCEAUX = RACINE / "data" / "morceaux.jsonl"

DOSSIER_DB = RACINE / "db" / "chroma"
FICHIER_PHRASES = RACINE / "db" / "phrases.npz"

DOSSIER_WEB = RACINE / "web"

DOSSIER_QUESTIONS = RACINE / "tests" / "questions"
