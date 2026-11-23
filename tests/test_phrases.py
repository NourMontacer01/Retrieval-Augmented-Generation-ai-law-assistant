"""Decoupage en phrases pour le surlignage : positions exactes dans le texte."""
from conformite.phrases import LONGUEUR_MIN_PHRASE, phrases_avec_positions


def test_positions_retombent_sur_les_phrases():
    texte = ("Le responsable du traitement tient un registre des activites. "
             "Ce registre comporte toutes les informations suivantes, sans exception.")
    positions = phrases_avec_positions(texte)
    assert [texte[d:f] for d, f in positions] == [
        "Le responsable du traitement tient un registre des activites.",
        "Ce registre comporte toutes les informations suivantes, sans exception.",
    ]


def test_un_fragment_court_est_colle_au_suivant():
    texte = "1.\nLe responsable du traitement met en oeuvre des mesures appropriees."
    positions = phrases_avec_positions(texte)
    assert len(positions) == 1
    assert texte[slice(*positions[0])] == texte


def test_chaque_ligne_d_une_enumeration_est_une_phrase():
    lignes = [
        "a) le traitement est necessaire a l'execution d'un contrat conclu",
        "b) le traitement est necessaire au respect d'une obligation legale",
    ]
    positions = phrases_avec_positions("\n".join(lignes))
    assert len(positions) == 2


def test_aucune_position_vide_et_ordre_croissant():
    texte = "Premiere phrase assez longue pour rester seule ici.\n\n\nDeuxieme phrase assez longue elle aussi."
    positions = phrases_avec_positions(texte)
    assert all(f > d for d, f in positions)
    assert positions == sorted(positions)
    assert all(f - d >= LONGUEUR_MIN_PHRASE for d, f in positions[:-1])


def test_texte_vide():
    assert phrases_avec_positions("") == []
