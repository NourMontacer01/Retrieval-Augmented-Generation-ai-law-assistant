"""API de l'interface web, avec une fausse recherche : pas de modele ni de base a charger."""
import pytest
from fastapi.testclient import TestClient

from conformite import app as module_app

PASSAGE = {
    "id": "rgpd-article-35-par-1", "reference": "RGPD — Article 35", "nature": "contraignant",
    "texte": "Une analyse d'impact est effectuee. Elle porte sur les risques eleves.",
    "source_id": "rgpd", "type_unite": "article", "numero": "35",
}


class FausseCollection:
    def get(self, where, include):
        numero = where["$and"][2]["numero"]
        if numero != "35":
            return {"ids": [], "documents": [], "metadatas": []}
        meta = {"source_titre": "RGPD", "titre_unite": "Analyse d'impact"}
        return {
            "ids": ["rgpd-article-35-par-2", "rgpd-article-35-par-1"],
            "documents": ["2. Deuxieme paragraphe.", "1. Premier paragraphe."],
            "metadatas": [meta | {"ordre": 2}, meta | {"ordre": 1}],
        }


class FausseRecherche:
    def __init__(self):
        self.phrases = {}
        self.appels = 0
        self.collection = FausseCollection()

    def vectoriser_question(self, question):
        return [0.0]

    def rechercher(self, question, k=5, **filtres):
        self.appels += 1
        return [dict(PASSAGE)]

    def surligner(self, question, passages):
        for p in passages:
            p["surlignage"] = {"debut": 0, "fin": 35}
        return passages


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(module_app, "Recherche", FausseRecherche)
    monkeypatch.setattr(module_app, "redaction_disponible", lambda: False)
    with TestClient(module_app.app) as c:
        yield c


def test_page_d_accueil(client):
    reponse = client.get("/")
    assert reponse.status_code == 200
    assert "text/html" in reponse.headers["content-type"]


def test_recherche_puis_cache(client):
    demande = {"question": "Quand faire une AIPD ?"}
    premiere = client.post("/api/recherche", json=demande).json()
    assert premiere["passages"][0]["id"] == PASSAGE["id"]
    assert premiere["cache"] is False
    assert premiere["redaction"] is False

    # Meme question, casse et espaces differents : servie par le cache
    seconde = client.post("/api/recherche", json={"question": "  quand faire une aipd ?  "}).json()
    assert seconde["cache"] is True
    assert module_app.etat["recherche"].appels == 1


def test_question_trop_courte_refusee(client):
    assert client.post("/api/recherche", json={"question": "ab"}).status_code == 422
    assert client.post("/api/recherche", json={"question": "abc", "k": 50}).status_code == 422


def test_surlignage(client):
    reponse = client.post("/api/surlignage", json={"question": "Quand faire une AIPD ?"}).json()
    assert reponse == {PASSAGE["id"]: {"debut": 0, "fin": 35}}


def test_synthese_sans_cle_api(client):
    assert client.post("/api/synthese", json={"question": "Quand faire une AIPD ?"}).status_code == 404


def test_unite_recomposee_dans_l_ordre(client):
    reponse = client.get("/api/unite/rgpd/article/35").json()
    assert reponse["texte"] == "1. Premier paragraphe.\n2. Deuxieme paragraphe."
    assert reponse["titre_unite"] == "Analyse d'impact"


def test_unite_introuvable(client):
    assert client.get("/api/unite/rgpd/article/999").status_code == 404


def test_cle_de_tri():
    ids = ["x-par-10", "x-par-2", "x-par-2-p10", "x-par-2-p2"]
    assert sorted(ids, key=module_app.cle_de_tri) == ["x-par-2", "x-par-2-p2", "x-par-2-p10", "x-par-10"]
