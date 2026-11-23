"""Etape 2b - retrouve les passages les plus proches d'une question, avec leurs etiquettes.

Principe : la question est transformee en vecteur avec le meme modele que les morceaux,
puis ChromaDB renvoie les morceaux dont le vecteur est le plus proche (similarite cosinus).
Les filtres sur les etiquettes (nature, source, type d'unite) s'appliquent AVANT le
classement : on ne cherche que parmi les morceaux autorises.

Usage (dossier du projet, terminal PowerShell) :
    .venv\\Scripts\\python -m conformite.recherche "Quand faut-il realiser une AIPD ?"
    .venv\\Scripts\\python -m conformite.recherche "systeme a haut risque" --source ai-act -k 3
"""
import argparse
import sys
from functools import lru_cache

import chromadb
import numpy as np

from conformite import phrases
from conformite.glossaire import enrichir, references_explicites, textes_nommes
# Une seule source de verite : memes modele, prefixes et base que pour l'indexation.
# Si on vectorisait la question avec un autre modele, les vecteurs seraient incomparables.
from conformite.index import COLLECTION, DOSSIER_DB, MODELE, PREFIXE_PASSAGE, PREFIXE_REQUETE
from conformite.motscles import BM25

# Les filtres proposes : ce sont les etiquettes posees au decoupage
FILTRES_AUTORISES = ("nature", "source_id", "type_unite", "juridiction", "autorite", "numero")
# Nombre de candidats pris dans chaque classement (sens, mots) avant fusion
CANDIDATS = 30
# Nombre maximum de morceaux d'un meme article dans les resultats
MAX_PAR_UNITE = 2
# Poids du classement par mots-cles dans la fusion (1.0 = autant que le sens)
POIDS_MOTS_CLES = 0.5
# Coefficient applique aux considerants (1.0 = aucune priorite aux articles)
POIDS_CONSIDERANT = 0.9


def correspond_aux_filtres(meta, filtres):
    return all(meta.get(champ) == valeur for champ, valeur in filtres.items() if valeur is not None)


class Recherche:
    """Charge le modele et la base une seule fois, puis repond a autant de questions qu'on veut.

    Charger le modele prend plusieurs secondes : evaluation.py posera des dizaines de
    questions, on ne veut pas le recharger a chaque fois.
    """

    def __init__(self, hybride=False, glossaire=True, references=True, priorite_articles=True,
                 diversite=True):
        if not DOSSIER_DB.exists():
            raise SystemExit(f"{DOSSIER_DB} absent - lance d'abord python -m conformite.index")
        from sentence_transformers import SentenceTransformer  # import lent, fait au dernier moment

        # Chaque amelioration peut etre coupee : evaluation.py --ablation mesure ainsi ce que
        # chacune apporte. Reglages par defaut = la meilleure combinaison mesuree.
        self.hybride, self.glossaire, self.diversite = hybride, glossaire, diversite
        self.references, self.priorite_articles = references, priorite_articles

        self.modele = SentenceTransformer(MODELE)
        client = chromadb.PersistentClient(path=str(DOSSIER_DB))
        self.collection = client.get_collection(COLLECTION)
        # Vecteurs des phrases precalcules par index.py (vide si pas encore faits)
        self.phrases = phrases.charger()
        # Une question deja posee n'est pas revectorisee (utile en demo et en evaluation)
        self.vectoriser_question = lru_cache(maxsize=256)(self._vectoriser_question)

        # Copie en memoire de tous les morceaux, pour la recherche par mots-cles
        tout = self.collection.get(include=["documents", "metadatas"])
        self.ids, self.textes, self.metas = tout["ids"], tout["documents"], tout["metadatas"]
        self.rang_de = {i: n for n, i in enumerate(self.ids)}
        # BM25 indexe la reference + le texte, comme le vecteur (texte_indexe)
        self.bm25 = BM25([f"{m.get('reference', '')} {t}" for t, m in zip(self.textes, self.metas)])

    def _vectoriser_question(self, question):
        # Prefixe "query: " obligatoire pour e5 (les morceaux ont ete indexes avec "passage: ")
        return tuple(self.modele.encode(PREFIXE_REQUETE + question, normalize_embeddings=True).tolist())

    def rechercher(self, question, k=5, **filtres):
        """Renvoie les k passages les plus pertinents, du plus au moins pertinent.

        filtres : par exemple nature="contraignant", source_id="rgpd", type_unite="article".
        """
        requete = enrichir(question) if self.glossaire else question
        vecteur = np.array(self.vectoriser_question(requete), dtype=np.float32)

        # 0. Le texte nomme dans la question ("... de l'AI Act ?") devient un filtre,
        #    sauf si l'utilisateur en a deja choisi un
        if self.references and not filtres.get("source_id"):
            nommes = textes_nommes(question)
            if len(nommes) == 1:
                filtres = {**filtres, "source_id": nommes.pop()}

        # 1. Candidats par le sens (vecteurs), filtres par ChromaDB
        par_sens = self.collection.query(
            query_embeddings=[vecteur.tolist()],
            n_results=CANDIDATS,
            where=construire_filtre(filtres),
            include=[],
        )["ids"][0]

        # 2. Fusion des classements (Reciprocal Rank Fusion) : chaque liste donne
        #    1 / (60 + rang) a ses documents. On additionne des rangs, pas des scores :
        #    inutile de comparer un cosinus et un score BM25, d'echelles differentes.
        listes = [(par_sens, 1.0)]
        if self.hybride:
            # Candidats par les mots exacts (BM25), avec les memes filtres
            scores = self.bm25.scores(requete)
            autorises = [n for n in scores if correspond_aux_filtres(self.metas[n], filtres)]
            par_mots = [self.ids[n] for n in sorted(autorises, key=scores.get, reverse=True)[:CANDIDATS]]
            listes.append((par_mots, POIDS_MOTS_CLES))
        fusion = {}
        for liste, poids in listes:
            for rang, identifiant in enumerate(liste):
                fusion[identifiant] = fusion.get(identifiant, 0) + poids / (60 + rang)

        # 3. Priorite aux articles : un considerant explique l'intention du legislateur,
        #    il n'oblige pas. A pertinence proche, l'article qui pose la regle passe devant.
        if self.priorite_articles:
            for identifiant in fusion:
                if self.metas[self.rang_de[identifiant]].get("type_unite") == "considerant":
                    fusion[identifiant] *= POIDS_CONSIDERANT
        classement = sorted(fusion, key=fusion.get, reverse=True)

        # 4. Reference explicite ("Que dit l'article 5 ?") : un numero seul n'a pas de sens
        #    pour un vecteur, on va donc chercher l'article directement et on le place en tete
        if self.references:
            cites = []
            for type_unite, numero in references_explicites(question):
                trouves = self.collection.get(
                    where=construire_filtre({**filtres, "type_unite": type_unite, "numero": numero}),
                    include=[],
                )["ids"]
                cites += sorted(trouves, key=lambda i: self.metas[self.rang_de[i]].get("ordre", 0))
            classement = cites + [i for i in classement if i not in cites]

        # 4. Diversite : au plus MAX_PAR_UNITE morceaux du meme article, pour que le
        #    top k couvre plusieurs articles au lieu de trois paragraphes du meme
        retenus, par_unite = [], {}
        for identifiant in classement:
            meta = self.metas[self.rang_de[identifiant]]
            unite = (meta.get("source_id"), meta.get("type_unite"), meta.get("numero"))
            if self.diversite and par_unite.get(unite, 0) >= MAX_PAR_UNITE:
                continue
            par_unite[unite] = par_unite.get(unite, 0) + 1
            retenus.append(identifiant)
            if len(retenus) == k:
                break

        # Score affiche : similarite cosinus entre la question et le passage (1 = identique),
        # recalculee pour tous les retenus, y compris ceux venus de BM25
        vecteurs = self.collection.get(ids=retenus, include=["embeddings"])
        cosinus = dict(zip(vecteurs["ids"], np.array(vecteurs["embeddings"]) @ vecteur))

        passages = []
        for identifiant in retenus:
            n = self.rang_de[identifiant]
            meta = self.metas[n]
            passages.append({
                "id": identifiant,
                "texte": self.textes[n],
                "reference": meta.get("reference", ""),
                "nature": meta.get("nature", ""),
                "autorite": meta.get("autorite", ""),
                "source_id": meta.get("source_id", ""),
                "type_unite": meta.get("type_unite", ""),
                "numero": meta.get("numero", ""),
                "url": meta.get("url", ""),
                "score": round(float(cosinus[identifiant]), 4),
            })
        return passages

    def surligner(self, question, passages):
        """Ajoute a chaque passage la phrase la plus proche de la question.

        Meme principe que la recherche, mais a l'echelle de la phrase : chaque phrase est
        comparee a la question. C'est une proximite de sens, pas un avis juridique : la
        phrase surlignee est celle qui "parle le plus" de la question.
        """
        requete = enrichir(question) if self.glossaire else question
        vecteur_question = np.array(self.vectoriser_question(requete), dtype=np.float32)
        for p in passages:
            if p["id"] in self.phrases:
                # Cas normal : vecteurs precalcules a l'indexation, aucun passage dans le modele
                positions, vecteurs = self.phrases[p["id"]]
            else:
                # Repli : morceau indexe sans ses phrases, on les vectorise maintenant et on garde
                positions = phrases.phrases_avec_positions(p["texte"])
                if not positions:
                    continue
                vecteurs = self.modele.encode(
                    [PREFIXE_PASSAGE + p["texte"][d:f] for d, f in positions],
                    normalize_embeddings=True,
                )
                self.phrases[p["id"]] = (positions, vecteurs)
            # vecteurs normalises : le produit scalaire est directement la similarite cosinus
            scores = vecteurs @ vecteur_question
            meilleur = int(scores.argmax())
            p["surlignage"] = {"debut": positions[meilleur][0], "fin": positions[meilleur][1]}
        return passages


def construire_filtre(filtres):
    """Traduit {"nature": "contraignant", "source_id": "rgpd"} en filtre ChromaDB.

    ChromaDB exige "$and" des qu'il y a plus d'une condition.
    """
    conditions = []
    for champ, valeur in filtres.items():
        if valeur is None:
            continue
        if champ not in FILTRES_AUTORISES:
            raise ValueError(f"filtre inconnu : {champ} (autorises : {', '.join(FILTRES_AUTORISES)})")
        conditions.append({champ: valeur})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def afficher(passages):
    for rang, p in enumerate(passages, 1):
        print(f"\n[{rang}] score {p['score']:.3f} | nature : {p['nature']} | {p['id']}")
        print(f"    {p['reference']}")
        apercu = p["texte"].replace("\n", " ")
        print(f"    {apercu[:300]}{'...' if len(apercu) > 300 else ''}")


def main():
    # La console Windows n'affiche pas toujours les accents des textes juridiques
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parseur = argparse.ArgumentParser(description="Recherche dans le corpus de conformite")
    parseur.add_argument("question")
    parseur.add_argument("-k", type=int, default=5, help="nombre de passages (defaut 5)")
    parseur.add_argument("--nature", help="ex : contraignant")
    parseur.add_argument("--source", dest="source_id", help="ex : rgpd, ai-act")
    parseur.add_argument("--type", dest="type_unite", help="article, annexe ou considerant")
    args = parseur.parse_args()

    recherche = Recherche()
    passages = recherche.rechercher(
        args.question, k=args.k,
        nature=args.nature, source_id=args.source_id, type_unite=args.type_unite,
    )
    print(f"Question : {args.question}")
    afficher(passages)


if __name__ == "__main__":
    main()
