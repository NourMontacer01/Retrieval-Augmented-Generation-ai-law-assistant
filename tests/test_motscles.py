"""BM25 ecrit a la main : normalisation des mots et classement."""
from conformite.motscles import BM25, mots


def test_mots_normalise():
    assert mots("Les Données personnelles") == ["donnee", "personnelle"]


def test_mots_retire_les_mots_vides_et_les_lettres_seules():
    assert mots("le responsable doit a") == ["responsable"]


def test_mots_courts_gardent_leur_s():
    # "lois" -> "loi" serait juste, mais "fois" -> "foi" ne le serait pas : on ne touche
    # qu'aux mots de plus de 4 lettres
    assert mots("des lois") == ["lois"]


def test_bm25_classe_le_document_pertinent_en_tete():
    textes = [
        "Le delegue a la protection des donnees est designe par le responsable.",
        "Les amendes administratives sont imposees par l'autorite de controle.",
        "Le sous-traitant agit pour le compte du responsable du traitement.",
    ]
    scores = BM25(textes).scores("amendes administratives")
    assert max(scores, key=scores.get) == 1


def test_bm25_ignore_les_documents_sans_mot_commun():
    scores = BM25(["chat noir", "chien blanc"]).scores("chat")
    assert set(scores) == {0}


def test_bm25_mot_rare_pese_plus_qu_un_mot_frequent():
    textes = ["donnees biometrie", "donnees courriel", "donnees adresse", "donnees telephone"]
    bm25 = BM25(textes)
    assert bm25.idf["biometrie"] > bm25.idf["donnee"]


def test_bm25_question_vide():
    assert BM25(["un texte"]).scores("") == {}
