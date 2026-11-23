"""Etape 4 - mesure si la recherche retrouve les bons articles.

On ne juge pas ici la redaction, seulement la recherche : si le bon article n'est pas
dans les passages, aucun modele ne pourra bien repondre.

Deux mesures :
- taux de reussite @k : part des questions ou au moins un passage attendu est dans les k premiers
- MRR (rang reciproque moyen) : 1 si le bon passage est 1er, 0.5 s'il est 2e, 0.33 s'il est 3e...
  Elle recompense un bon passage place tot, pas seulement present.

Les questions sont dans test/questions.json (format : voir test/questions_modele.json).
Usage (dossier du projet) :
    .venv\\Scripts\\python -m conformite.evaluation
    .venv\\Scripts\\python -m conformite.evaluation -k 10
"""
import argparse
import json
import pathlib
import sys

from conformite.chemins import DOSSIER_QUESTIONS
from conformite.recherche import Recherche

FICHIER_QUESTIONS = DOSSIER_QUESTIONS / "questions.json"
FICHIER_MODELE = DOSSIER_QUESTIONS / "questions_modele.json"


def correspond(identifiant, attendu):
    """'rgpd-article-35' doit valider 'rgpd-article-35' et 'rgpd-article-35-par-7',
    mais pas 'rgpd-article-350'."""
    return identifiant == attendu or identifiant.startswith(attendu + "-")


def rang_du_premier_bon(identifiants, attendus):
    for rang, identifiant in enumerate(identifiants, 1):
        if any(correspond(identifiant, a) for a in attendus):
            return rang
    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parseur = argparse.ArgumentParser()
    parseur.add_argument("-k", type=int, default=5)
    parseur.add_argument("--fichier", default=str(FICHIER_QUESTIONS))
    parseur.add_argument("--ablation", action="store_true",
                         help="mesure chaque amelioration de la recherche separement")
    args = parseur.parse_args()

    fichier = pathlib.Path(args.fichier)
    if not fichier.exists():
        raise SystemExit(f"{fichier} absent - copie {FICHIER_MODELE} et ecris tes questions")
    questions = json.loads(fichier.read_text(encoding="utf-8"))

    recherche = Recherche()

    # Questions hors corpus ("attendus": []) : aucun bon passage n'existe, donc on ne peut pas
    # les compter dans la reussite. On note le meilleur score obtenu : s'il est aussi haut que
    # pour une vraie question, un seuil de score ne suffira pas a dire "je ne sais pas".
    hors_corpus = [q for q in questions if not q["attendus"]]
    questions = [q for q in questions if q["attendus"]]

    if args.ablation:
        # Un seul modele charge ; on active les ameliorations une a une
        # Ajouts cumules : chaque ligne = la precedente + une amelioration
        reglages = ["glossaire", "references", "priorite_articles", "diversite", "hybride"]
        configurations = [
            ("vecteurs seuls", []),
            ("+ glossaire", reglages[:1]),
            ("+ references explicites", reglages[:2]),
            ("+ priorite aux articles", reglages[:3]),
            ("+ diversite", reglages[:4]),
            ("+ hybride BM25", reglages[:5]),
        ]
        print(f"{len(questions)} questions, k = {args.k}\n")
        print(f"{'configuration':<26}{'reussite':>10}{'MRR':>8}")
        for nom, actifs in configurations:
            for r in reglages:
                setattr(recherche, r, r in actifs)
            reussite, mrr = mesurer(recherche, questions, args.k, bavard=False)
            print(f"{nom:<26}{reussite:>10.1%}{mrr:>8.3f}")
        return

    for q in hors_corpus:
        passages = recherche.rechercher(q["question"], k=1, **q.get("filtres", {}))
        meilleur = passages[0] if passages else None
        print(f"  HORS score {meilleur['score']:.3f} | {q['question'][:70]}")
        print(f"       plus proche : {meilleur['id']}")

    reussite, mrr = mesurer(recherche, questions, args.k, bavard=True)
    print(f"\n{len(questions)} questions, k = {args.k}")
    print(f"taux de reussite @{args.k} : {reussite:.1%}")
    print(f"MRR : {mrr:.3f}")


def mesurer(recherche, questions, k, bavard):
    reussites, somme_rr = 0, 0.0
    for q in questions:
        passages = recherche.rechercher(q["question"], k=k, **q.get("filtres", {}))
        ids = [p["id"] for p in passages]
        rang = rang_du_premier_bon(ids, q["attendus"])

        if rang:
            reussites += 1
            somme_rr += 1 / rang
            if bavard:
                print(f"  OK   rang {rang} | {q['question'][:70]}")
        elif bavard:
            print(f"  RATE        | {q['question'][:70]}")
            print(f"       attendu {q['attendus']}, obtenu {ids[:3]}")

    n = len(questions)
    return reussites / n, somme_rr / n


if __name__ == "__main__":
    main()
