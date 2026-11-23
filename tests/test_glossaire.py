"""Glossaire, textes nommes et references explicites dans la question."""
from conformite.glossaire import enrichir, references_explicites, sans_accents, textes_nommes


def test_sans_accents():
    assert sans_accents("Délégué à la protection") == "Delegue a la protection"


def test_enrichir_ajoute_la_formulation_du_texte():
    q = "Quand faut-il faire une AIPD ?"
    assert enrichir(q) == f"{q} (analyse d'impact relative a la protection des donnees)"


def test_enrichir_accepte_les_accords():
    assert "violation de donnees" in enrichir("Mon site a été piraté")
    assert "violation de donnees" in enrichir("des comptes piratés")


def test_enrichir_mot_entier_seulement():
    assert enrichir("adpo inconnu") == "adpo inconnu"


def test_enrichir_ne_repete_pas_une_traduction():
    resultat = enrichir("fuite de donnees apres un piratage")
    assert resultat.count("violation de donnees a caractere personnel") == 1


def test_enrichir_sans_terme_connu_ne_change_rien():
    assert enrichir("Bonjour") == "Bonjour"


def test_textes_nommes():
    assert textes_nommes("Que dit l'AI Act sur la transparence ?") == {"ai-act"}
    assert textes_nommes("RGPD et Data Act") == {"rgpd", "data-act"}
    assert textes_nommes("Que dit le règlement 2016/679 ?") == {"rgpd"}
    assert textes_nommes("Une question générale") == set()


def test_references_explicites():
    assert references_explicites("Que dit l'Article 5 ?") == [("article", "5")]
    assert references_explicites("article 14 bis") == [("article", "14 bis")]
    assert references_explicites("annexe iii de l'AI Act") == [("annexe", "III")]
    assert references_explicites("les articles en general") == []
