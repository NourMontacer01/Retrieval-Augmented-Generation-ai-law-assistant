"""Indexation incrementale : seuls les morceaux nouveaux ou modifies sont revectorises.

Le modele est remplace par un faux vectoriseur : le test verifie la logique, pas le sens.
"""
import pytest

from conformite import index
from conformite.index import construire, empreinte, nettoyer_metadonnees


class FauxVectoriseur:
    def __init__(self):
        self.appels = []

    def __call__(self, textes, prefixe):
        self.appels.append(list(textes))
        return [[float(len(t)), 1.0, 0.5] for t in textes]


def morceau(identifiant, texte):
    return {"id": identifiant, "texte": texte, "texte_indexe": f"Ref\n{texte}",
            "source_id": "rgpd", "type_unite": "article", "numero": "1", "paragraphe": ""}


@pytest.fixture
def base_temporaire(monkeypatch, tmp_path):
    monkeypatch.setattr(index, "DOSSIER_DB", tmp_path / "chroma")


def test_nettoyer_metadonnees_retire_vides_et_convertit():
    propre = nettoyer_metadonnees({"source_id": "rgpd", "paragraphe": "", "chapitre": None, "ordre": 3})
    assert propre == {"source_id": "rgpd", "ordre": 3}


def test_empreinte_change_avec_le_texte():
    assert empreinte(morceau("a", "texte")) == empreinte(morceau("b", "texte"))
    assert empreinte(morceau("a", "texte")) != empreinte(morceau("a", "texte modifie"))


def test_indexation_incrementale(base_temporaire):
    vectoriser = FauxVectoriseur()
    corpus = [morceau("rgpd-article-1", "un"), morceau("rgpd-article-2", "deux")]

    collection = construire(corpus, vectoriser)
    assert collection.count() == 2
    assert len(vectoriser.appels[-1]) == 2

    # Rien n'a change : aucun appel au modele
    construire(corpus, vectoriser)
    assert len(vectoriser.appels) == 1

    # Un texte modifie, un ajoute, un supprime : seuls les deux premiers sont vectorises
    corpus = [morceau("rgpd-article-2", "deux modifie"), morceau("rgpd-article-3", "trois")]
    collection = construire(corpus, vectoriser)
    assert len(vectoriser.appels) == 2
    assert sorted(vectoriser.appels[-1]) == ["Ref\ndeux modifie", "Ref\ntrois"]
    assert sorted(collection.get()["ids"]) == ["rgpd-article-2", "rgpd-article-3"]
