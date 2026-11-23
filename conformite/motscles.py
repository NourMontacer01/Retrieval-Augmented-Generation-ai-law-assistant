"""Recherche par mots-cles (BM25), complement de la recherche par vecteurs.

Les vecteurs captent le sens ("fuite" ~ "violation") mais diluent les termes precis :
"sous-traitant", "article 34", "72 heures". BM25 fait l'inverse : il recompense les mots
exacts, d'autant plus qu'ils sont rares dans le corpus.

Score BM25 d'un document pour une question = somme, pour chaque mot de la question, de :
    idf(mot) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * longueur / longueur_moyenne))
- idf : un mot rare ("sous-traitant") pese plus qu'un mot frequent ("donnees")
- tf : nombre d'occurrences du mot dans le document, avec un effet de saturation (k1)
- b : penalise les documents longs, qui contiennent "par hasard" plus de mots
"""
import math
import re
from collections import Counter, defaultdict

from conformite.glossaire import sans_accents

# Mots trop frequents pour aider a distinguer un passage d'un autre
MOTS_VIDES = set("""
le la les un une des du de d l a au aux et ou en dans par pour sur avec sans sous ce cette ces
qui que quoi dont est sont etre a ont il elle ils elles on se sa son ses leur leurs ne pas plus
y je tu nous vous mon ma mes peut peuvent doit doivent faut quel quelle quels quelles comment
quand si tout tous toute toutes autre autres meme lorsque ainsi afin entre cas
""".split())


def mots(texte):
    """Texte -> liste de mots normalises : minuscules, sans accents, pluriel simple retire."""
    resultat = []
    for mot in re.findall(r"\w+", sans_accents(texte.lower())):
        if mot in MOTS_VIDES or len(mot) < 2:
            continue
        if len(mot) > 4 and mot.endswith(("s", "x")):
            mot = mot[:-1]                       # "donnees" et "donnee" -> meme mot
        resultat.append(mot)
    return resultat


class BM25:
    def __init__(self, textes, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        documents = [Counter(mots(t)) for t in textes]
        self.longueurs = [sum(d.values()) for d in documents]
        self.longueur_moyenne = sum(self.longueurs) / max(len(documents), 1)
        # Index inverse : pour chaque mot, les documents qui le contiennent et combien de fois
        self.index = defaultdict(list)
        for numero, doc in enumerate(documents):
            for mot, tf in doc.items():
                self.index[mot].append((numero, tf))
        n = len(documents)
        self.idf = {m: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for m, p in self.index.items()}

    def scores(self, question):
        """Renvoie {numero du document: score} pour les documents qui partagent un mot."""
        resultat = defaultdict(float)
        for mot in set(mots(question)):
            for numero, tf in self.index.get(mot, []):
                norme = 1 - self.b + self.b * self.longueurs[numero] / self.longueur_moyenne
                resultat[numero] += self.idf[mot] * tf * (self.k1 + 1) / (tf + self.k1 * norme)
        return resultat
