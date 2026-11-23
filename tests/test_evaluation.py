"""Metriques d'evaluation : correspondance des identifiants et rang du premier bon passage."""
from conformite.evaluation import correspond, rang_du_premier_bon


def test_correspond_accepte_les_sous_morceaux():
    assert correspond("rgpd-article-35", "rgpd-article-35")
    assert correspond("rgpd-article-35-par-7", "rgpd-article-35")
    assert correspond("ai-act-annexe-III-par-1-p2", "ai-act-annexe-III")


def test_correspond_refuse_un_autre_numero():
    assert not correspond("rgpd-article-350", "rgpd-article-35")
    assert not correspond("rgpd-article-3", "rgpd-article-35")


def test_rang_du_premier_bon():
    ids = ["rgpd-article-28", "rgpd-considerant-81", "rgpd-article-4-par-7"]
    assert rang_du_premier_bon(ids, ["rgpd-article-4"]) == 3
    assert rang_du_premier_bon(ids, ["rgpd-article-4", "rgpd-article-28"]) == 1
    assert rang_du_premier_bon(ids, ["rgpd-article-99"]) is None
    assert rang_du_premier_bon([], ["rgpd-article-4"]) is None
