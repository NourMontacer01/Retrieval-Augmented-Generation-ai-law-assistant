"""Construction du prompt : passages numerotes, nature juridique, consignes de cadrage."""
from conformite.reponse import CONSIGNES, bloc_passages, construire_messages

PASSAGES = [
    {"reference": "RGPD — Article 35", "nature": "contraignant", "texte": "Analyse d'impact."},
    {"reference": "Lignes directrices", "nature": "inconnue", "texte": "Recommandation."},
]


def test_bloc_passages_numerote_pour_citer():
    bloc = bloc_passages(PASSAGES)
    assert bloc.startswith("[1] RGPD — Article 35")
    assert "[2] Lignes directrices" in bloc
    assert "Analyse d'impact." in bloc


def test_nature_inconnue_affichee_telle_quelle():
    assert "Nature : inconnue" in bloc_passages(PASSAGES)


def test_construire_messages():
    messages = construire_messages("Quand faire une AIPD ?", PASSAGES)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[0]["content"] == CONSIGNES
    assert messages[1]["content"].endswith("Question : Quand faire une AIPD ?")


def test_les_consignes_gardent_le_cadrage():
    # L'outil oriente, il ne qualifie pas juridiquement : la consigne ne doit pas disparaitre
    assert "qualifi" in CONSIGNES.lower()
