"""Decoupage : un morceau par article, considerant ou annexe, sous-decoupe si trop long."""
from pathlib import Path

import pytest

from conformite import decoupage
from conformite.decoupage import (
    SEUIL_SOUS_DECOUPAGE, decouper, lignes_propres, par_paragraphe, par_phrases,
    reference, sous_decouper, traiter,
)

DOSSIER_ECHANTILLON = Path(__file__).parent / "decoupage"
SOURCE = {
    "id": "echantillon", "titre": "Echantillon de test", "url": "local",
    "nature": "contraignant", "autorite": "Union europeenne", "juridiction": "UE",
    "date": "2016-04-27", "format": "txt",
}


@pytest.fixture
def morceaux_echantillon(monkeypatch):
    monkeypatch.setattr(decoupage, "DOSSIER_BRUT", DOSSIER_ECHANTILLON)
    return traiter(SOURCE)


def test_lignes_propres_retire_les_marqueurs_eurlex():
    lignes = lignes_propres(DOSSIER_ECHANTILLON / "echantillon.txt")
    assert "►B" not in lignes and "◄" not in lignes
    assert "Article 32" in lignes            # "►M1" retire, l'en-tete reste
    assert all(l == l.strip() and l for l in lignes)


def test_decouper_reconnait_les_trois_types_d_unite():
    lignes = [
        "(1) Premier considerant.",
        "(2) Deuxieme considerant.",
        "CHAPITRE I", "Article premier", "Objet", "1. Texte de l'article.",
        "ANNEXE III", "Systemes a haut risque", "1. Biometrie.",
    ]
    morceaux = decouper(lignes)
    types = [(m["type_unite"], m["numero"]) for m in morceaux]
    assert types == [("considerant", "1"), ("considerant", "2"), ("article", "1"), ("annexe", "III")]
    article = morceaux[2]
    assert article["titre_unite"] == "Objet"
    assert article["chapitre"] == "CHAPITRE I"


def test_bis_sur_la_ligne_suivante_fait_partie_du_numero():
    morceaux = decouper(["Article 14", "bis", "Titre", "Corps de l'article."])
    assert morceaux[0]["numero"] == "14 bis"
    assert morceaux[0]["titre_unite"] == "Titre"


def test_un_considerant_apres_le_premier_article_n_est_pas_un_considerant():
    morceaux = decouper(["Article 1", "Titre", "(3) point d'enumeration"])
    assert [m["type_unite"] for m in morceaux] == ["article"]
    assert "(3) point d'enumeration" in morceaux[0]["texte"]


def test_par_paragraphe_coupe_aussi_le_numero_seul_sur_sa_ligne():
    texte = "1) premiere definition\n2)\nseconde definition"
    blocs = par_paragraphe(texte)
    assert [n for n, _ in blocs] == ["1", "2"]
    assert "seconde definition" in blocs[1][1]


def test_par_paragraphe_sans_structure_renvoie_le_texte_entier():
    assert par_paragraphe("un texte\nsans numero") == [("", "un texte\nsans numero")]


def test_par_phrases_respecte_la_cible_sans_couper_une_phrase():
    phrase = "Une phrase de test assez longue pour remplir la cible. "
    parties = par_phrases(phrase * 100, cible=500)
    assert len(parties) > 1
    assert all(len(p) <= 500 for p in parties)
    assert all(p.endswith(".") for p in parties)


def test_sous_decouper_ne_touche_pas_un_texte_court():
    assert sous_decouper("court") == [("", "", "court")]


def test_sous_decouper_un_long_article_numerote():
    texte = "\n".join(f"{i}. " + "mot " * 200 for i in range(1, 6))
    assert len(texte) > SEUIL_SOUS_DECOUPAGE
    resultat = sous_decouper(texte)
    assert [p for p, _, _ in resultat] == ["1", "2", "3", "4", "5"]


def test_reference_situe_le_morceau():
    morceau = {"type_unite": "article", "numero": "35", "titre_unite": "Analyse d'impact"}
    assert reference({"titre": "RGPD"}, morceau, "7", "") == "RGPD — Article 35 — paragraphe 7 — Analyse d'impact"


def test_traiter_l_echantillon(morceaux_echantillon):
    ids = [m["id"] for m in morceaux_echantillon]
    assert "echantillon-considerant-5" in ids
    assert "echantillon-article-1" in ids
    assert "echantillon-article-32" in ids
    assert "echantillon-annexe-III" in ids
    # l'article 4 depasse le seuil : sous-decoupe par definition, "2)" seul sur sa ligne compris
    assert any(i.startswith("echantillon-article-4-par-2") for i in ids)


def test_identifiants_uniques_et_ordre_croissant(morceaux_echantillon):
    ids = [m["id"] for m in morceaux_echantillon]
    assert len(ids) == len(set(ids))
    assert [m["ordre"] for m in morceaux_echantillon] == list(range(len(ids)))


def test_texte_indexe_commence_par_la_reference(morceaux_echantillon):
    for m in morceaux_echantillon:
        assert m["texte_indexe"] == f"{m['reference']}\n{m['texte']}"
        assert m["nature"] == "contraignant"


def test_identifiant_en_double_recoit_un_suffixe(monkeypatch, tmp_path):
    # Annexe en sections : les paragraphes repartent de 1, le meme identifiant reviendrait
    long = "mot " * 400
    (tmp_path / "doublon.txt").write_text(
        "ANNEXE VIII\nTitre\nSection A\n1. " + long + "\n2. " + long +
        "\nSection B\n1. " + long + "\n2. " + long, encoding="utf-8")
    monkeypatch.setattr(decoupage, "DOSSIER_BRUT", tmp_path)
    ids = [m["id"] for m in traiter(SOURCE | {"id": "doublon"})]
    assert len(ids) == len(set(ids))
    assert any(i.endswith("-occ2") for i in ids)
