"""Construit la version en ligne : un site statique ou la recherche tourne dans le navigateur.

Pourquoi : un serveur Python avec le modele demande un hebergement payant. Ici, le
navigateur du visiteur charge le meme modele (multilingual-e5-base, version ONNX) et
compare la question aux vecteurs deja calcules, exportes depuis ChromaDB.

Usage (dossier du projet) :
    .venv\\Scripts\\python -m hebergement.exporter
Resultat : hebergement/site/, pret a publier (hebergement.publier).
"""
import json
import shutil

import chromadb
import numpy as np

from conformite import phrases
from conformite.chemins import DOSSIER_DB, DOSSIER_WEB, RACINE
from conformite.glossaire import GLOSSAIRE, NOMS_DES_TEXTES
from conformite.index import COLLECTION
from conformite.recherche import CANDIDATS, MAX_PAR_UNITE, POIDS_CONSIDERANT

DOSSIER_HEBERGEMENT = RACINE / "hebergement"
DOSSIER_SITE = DOSSIER_HEBERGEMENT / "site"
# Champs utiles a l'interface : le reste des metadonnees ne sert qu'a l'indexation
CHAMPS = ["reference", "nature", "autorite", "source_id", "source_titre", "type_unite", "numero",
          "titre_unite", "chapitre", "section", "version", "url", "ordre"]


def exporter_morceaux(dossier):
    collection = chromadb.PersistentClient(path=str(DOSSIER_DB)).get_collection(COLLECTION)
    tout = collection.get(include=["documents", "metadatas", "embeddings"])
    morceaux = [{"id": i, "texte": t, **{c: m.get(c, "") for c in CHAMPS}}
                for i, t, m in zip(tout["ids"], tout["documents"], tout["metadatas"])]
    # float16 : 2,7 Mo au lieu de 5,5 ; l'ordre des vecteurs suit celui des morceaux
    np.asarray(tout["embeddings"], dtype=np.float16).tofile(dossier / "vecteurs.bin")
    (dossier / "morceaux.json").write_text(json.dumps(morceaux, ensure_ascii=False), encoding="utf-8")
    return [m["id"] for m in morceaux]


def exporter_phrases(dossier, ids):
    cache = phrases.charger()
    positions, vecteurs = {}, []
    for identifiant in ids:
        if identifiant in cache:
            pos, vec = cache[identifiant]
            positions[identifiant] = [list(p) for p in pos]
            vecteurs.append(vec)
    np.concatenate(vecteurs).astype(np.float16).tofile(dossier / "phrases.bin")
    (dossier / "phrases.json").write_text(json.dumps(positions), encoding="utf-8")
    return sum(len(p) for p in positions.values())


def main():
    if DOSSIER_SITE.exists():
        shutil.rmtree(DOSSIER_SITE)
    donnees = DOSSIER_SITE / "donnees"
    statique = DOSSIER_SITE / "static"
    donnees.mkdir(parents=True)
    statique.mkdir()

    ids = exporter_morceaux(donnees)
    nb_phrases = exporter_phrases(donnees, ids)
    # Memes reglages et meme glossaire que la version Python : une seule source de verite
    (donnees / "reglages.json").write_text(json.dumps({
        "glossaire": GLOSSAIRE, "noms_des_textes": NOMS_DES_TEXTES, "candidats": CANDIDATS,
        "max_par_unite": MAX_PAR_UNITE, "poids_considerant": POIDS_CONSIDERANT,
    }, ensure_ascii=False), encoding="utf-8")

    for nom in ("style.css", "app.js"):
        shutil.copy(DOSSIER_WEB / nom, statique / nom)
    shutil.copy(DOSSIER_HEBERGEMENT / "moteur.js", statique / "moteur.js")

    # Meme page que la version locale, avec le moteur charge avant app.js
    page = (DOSSIER_WEB / "index.html").read_text(encoding="utf-8")
    page = page.replace('<script src="/static/app.js"></script>',
                        '<script src="static/moteur.js"></script>\n<script src="static/app.js"></script>')
    page = page.replace('href="/static/style.css"', 'href="static/style.css"')
    (DOSSIER_SITE / "index.html").write_text(page, encoding="utf-8")
    shutil.copy(DOSSIER_HEBERGEMENT / "README.md", DOSSIER_SITE / "README.md")

    taille = sum(f.stat().st_size for f in DOSSIER_SITE.rglob("*") if f.is_file()) / 1e6
    print(f"{len(ids)} morceaux, {nb_phrases} phrases -> {DOSSIER_SITE} ({taille:.1f} Mo)")


if __name__ == "__main__":
    main()
