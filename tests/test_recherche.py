"""Recherche : filtres ChromaDB, puis quelques questions sur la vraie base.

Les tests marques "corpus" chargent le modele et la base (une dizaine de secondes).
Ils sont ignores si la base n'a pas ete construite (lancer.bat, option 2).
"""
import pytest

from conformite.chemins import DOSSIER_DB
from conformite.recherche import construire_filtre, correspond_aux_filtres


def test_construire_filtre_une_condition():
    assert construire_filtre({"source_id": "rgpd", "nature": None}) == {"source_id": "rgpd"}


def test_construire_filtre_plusieurs_conditions():
    filtre = construire_filtre({"source_id": "rgpd", "type_unite": "article"})
    assert filtre == {"$and": [{"source_id": "rgpd"}, {"type_unite": "article"}]}


def test_construire_filtre_vide():
    assert construire_filtre({}) is None
    assert construire_filtre({"source_id": None}) is None


def test_construire_filtre_refuse_un_champ_inconnu():
    with pytest.raises(ValueError, match="filtre inconnu"):
        construire_filtre({"mot_de_passe": "x"})


def test_correspond_aux_filtres():
    meta = {"source_id": "rgpd", "type_unite": "article"}
    assert correspond_aux_filtres(meta, {"source_id": "rgpd", "nature": None})
    assert not correspond_aux_filtres(meta, {"source_id": "ai-act"})


# ---------- sur la vraie base ----------

@pytest.fixture(scope="module")
def recherche():
    if not DOSSIER_DB.exists():
        pytest.skip("base absente : construire la base avant ces tests")
    from conformite.recherche import Recherche
    return Recherche()


def ids(passages):
    return [p["id"] for p in passages]


@pytest.mark.corpus
@pytest.mark.parametrize("question, attendu", [
    ("Quand faut-il realiser une AIPD ?", "rgpd-article-35"),
    ("Quelles pratiques d'IA sont interdites ?", "ai-act-article-5"),
    ("Dans quel delai notifier une fuite de donnees a la CNIL ?", "rgpd-article-33"),
    ("Que dit l'article 17 du RGPD ?", "rgpd-article-17"),
])
def test_questions_de_reference(recherche, question, attendu):
    trouves = ids(recherche.rechercher(question, k=5))
    assert any(i == attendu or i.startswith(attendu + "-") for i in trouves), trouves


@pytest.mark.corpus
def test_filtre_par_source(recherche):
    passages = recherche.rechercher("transparence", k=5, source_id="ai-act")
    assert passages and all(p["source_id"] == "ai-act" for p in passages)


@pytest.mark.corpus
def test_diversite_au_plus_deux_morceaux_par_unite(recherche):
    passages = recherche.rechercher("droits de la personne concernee", k=10)
    unites = [(p["source_id"], p["type_unite"], p["numero"]) for p in passages]
    assert all(unites.count(u) <= 2 for u in unites)


@pytest.mark.corpus
def test_surlignage_dans_le_passage(recherche):
    passages = recherche.rechercher("Quand faut-il realiser une AIPD ?", k=3)
    recherche.surligner("Quand faut-il realiser une AIPD ?", passages)
    for p in passages:
        debut, fin = p["surlignage"]["debut"], p["surlignage"]["fin"]
        assert 0 <= debut < fin <= len(p["texte"])
