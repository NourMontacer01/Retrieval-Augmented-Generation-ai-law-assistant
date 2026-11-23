"""Interface web : une page pour poser une question et lire les articles cites.

Usage (dossier du projet, terminal PowerShell) :
    .venv\\Scripts\\python -m conformite.app
puis ouvrir http://127.0.0.1:8000
"""
import re
import sys
import time
import webbrowser
from collections import OrderedDict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from conformite import phrases
from conformite.recherche import Recherche
from conformite.reponse import appeler_modele_en_flux, construire_messages, redaction_disponible

from conformite.chemins import DOSSIER_WEB as DOSSIER_STATIC
TAILLE_CACHE = 256
PORT = 8000
ADRESSE = f"http://127.0.0.1:{PORT}"
etat = {}


@asynccontextmanager
async def demarrage(app):
    # Modele et base charges une seule fois au lancement du serveur, pas a chaque question
    etat["recherche"] = Recherche()
    etat["cache"] = OrderedDict()
    # Premiere vectorisation "a blanc" : le modele alloue sa memoire maintenant,
    # pas pendant la premiere vraie question
    etat["recherche"].vectoriser_question("echauffement")
    nb_phrases_au_depart = len(etat["recherche"].phrases)
    print(f"\nPret : ouvrir {ADRESSE}  (Ctrl+C pour arreter)\n")
    if "--ouvrir" in sys.argv:
        # Le navigateur s'ouvre une fois le modele charge, pas avant : sinon page d'erreur
        webbrowser.open(ADRESSE)
    yield
    # A l'arret du serveur : on garde les phrases vectorisees pendant la session,
    # le prochain lancement n'aura pas a les recalculer
    if len(etat["recherche"].phrases) > nb_phrases_au_depart:
        phrases.enregistrer(etat["recherche"].phrases)


app = FastAPI(lifespan=demarrage)
app.mount("/static", StaticFiles(directory=DOSSIER_STATIC), name="static")


class Demande(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    k: int = Field(default=5, ge=1, le=15)
    source_id: str | None = None
    type_unite: str | None = None


@app.get("/")
def accueil():
    return FileResponse(DOSSIER_STATIC / "index.html")


def passages_pour(demande):
    """Recherche + surlignage, avec cache : une question deja posee repond sans calcul.

    Le cache sert aussi a /api/synthese : la redaction reutilise les passages deja trouves
    au lieu de relancer la recherche.
    """
    cle = (demande.question.strip().lower(), demande.k, demande.source_id or None, demande.type_unite or None)
    cache = etat["cache"]
    if cle in cache:
        cache.move_to_end(cle)
        return cache[cle], True

    passages = etat["recherche"].rechercher(
        demande.question, k=demande.k,
        source_id=demande.source_id or None, type_unite=demande.type_unite or None,
    )
    cache[cle] = passages
    if len(cache) > TAILLE_CACHE:
        cache.popitem(last=False)       # on oublie la question la plus ancienne
    return passages, False


@app.post("/api/recherche")
def api_recherche(demande: Demande):
    """Etape rapide (local, une fraction de seconde) : les passages arrivent tout de suite."""
    debut = time.perf_counter()
    passages, depuis_cache = passages_pour(demande)
    return {
        "passages": passages,
        "redaction": redaction_disponible(),
        "duree_ms": round((time.perf_counter() - debut) * 1000),
        "cache": depuis_cache,
    }


@app.post("/api/surlignage")
def api_surlignage(demande: Demande):
    """Etape separee : la phrase la plus proche de la question, dans chaque passage.

    Separee de /api/recherche pour ne pas retarder l'affichage des passages : si les
    phrases n'ont pas ete precalculees (index.py --phrases), ce calcul prend 2 a 3 s.
    """
    passages, _ = passages_pour(demande)
    if any("surlignage" not in p for p in passages):
        etat["recherche"].surligner(demande.question, passages)   # memorise dans le cache
    return {p["id"]: p.get("surlignage") for p in passages}


@app.post("/api/synthese")
def api_synthese(demande: Demande):
    """Etape lente (modele distant) : le texte est envoye au fil de sa redaction."""
    passages, _ = passages_pour(demande)
    if not passages or not redaction_disponible():
        raise HTTPException(404, "pas de redaction possible")
    flux = appeler_modele_en_flux(construire_messages(demande.question, passages))
    return StreamingResponse(flux, media_type="text/plain; charset=utf-8")


def cle_de_tri(identifiant):
    """Remet les morceaux d'un article dans l'ordre : par-2 avant par-10, p2 avant p10."""
    return [int(n) for n in re.findall(r"(?:par-|-p)(\d+)", identifiant)]


@app.get("/api/unite/{source_id}/{type_unite}/{numero}")
def unite(source_id: str, type_unite: str, numero: str):
    """Recompose un article (ou annexe, considerant) entier a partir de ses morceaux."""
    resultat = etat["recherche"].collection.get(
        where={"$and": [{"source_id": source_id}, {"type_unite": type_unite}, {"numero": numero}]},
        include=["documents", "metadatas"],
    )
    if not resultat["ids"]:
        raise HTTPException(404, "unite introuvable")

    # "ordre" = rang du morceau dans le texte d'origine ; a defaut, numeros de l'identifiant
    morceaux = sorted(zip(resultat["ids"], resultat["documents"], resultat["metadatas"]),
                      key=lambda m: (m[2].get("ordre", 0), cle_de_tri(m[0])))
    meta = morceaux[0][2]
    return {
        "source_titre": meta.get("source_titre", ""),
        "type_unite": type_unite,
        "numero": numero,
        "titre_unite": meta.get("titre_unite", ""),
        "chapitre": meta.get("chapitre", ""),
        "section": meta.get("section", ""),
        "nature": meta.get("nature", ""),
        "version": meta.get("version", ""),
        "url": meta.get("url", ""),
        "texte": "\n".join(doc for _, doc, _ in morceaux),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
