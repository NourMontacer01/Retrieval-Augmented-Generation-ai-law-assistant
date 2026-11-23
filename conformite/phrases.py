"""Phrases des passages, pour le surlignage.

Le surlignage compare chaque phrase d'un passage a la question. Vectoriser ces phrases a
chaque question coute cher (le modele tourne sur processeur) : on les vectorise une fois
pour toutes pendant l'indexation et on les garde dans db/phrases.npz.
A la question, il ne reste qu'un produit de matrices : quelques millisecondes.
"""
import pathlib
import re

import numpy as np

from conformite.chemins import FICHIER_PHRASES

# Coupe un passage en phrases : apres . ; : ! ? ou a chaque retour a la ligne
# (dans les textes juridiques, chaque point d'une enumeration "a)", "b)" est sur sa ligne)
RE_SEPARATEUR = re.compile(r"(?<=[.;:!?])[ \t]+|\n+")
# Un fragment plus court ("1.", "a)") n'a pas de sens seul : il est colle au suivant
LONGUEUR_MIN_PHRASE = 40


def phrases_avec_positions(texte):
    """Renvoie [(debut, fin), ...] : la position de chaque phrase dans le texte.

    On garde des positions plutot que des copies du texte : l'interface pourra ainsi
    surligner exactement le bon endroit, meme si la phrase se repete ailleurs.
    """
    positions, debut = [], 0
    for separateur in RE_SEPARATEUR.finditer(texte):
        positions.append((debut, separateur.start()))
        debut = separateur.end()
    positions.append((debut, len(texte)))

    fusionnees = []
    for debut, fin in positions:
        if fin <= debut:
            continue
        if fusionnees and fusionnees[-1][1] - fusionnees[-1][0] < LONGUEUR_MIN_PHRASE:
            fusionnees[-1] = (fusionnees[-1][0], fin)
        else:
            fusionnees.append((debut, fin))
    return fusionnees


def charger():
    """db/phrases.npz -> {id du morceau: (positions, vecteurs)}. Dictionnaire vide si absent."""
    if not FICHIER_PHRASES.exists():
        return {}
    d = np.load(FICHIER_PHRASES)
    cache = {}
    # Les phrases d'un meme morceau sont contigues : on decoupe les tableaux par morceau
    frontieres = np.flatnonzero(np.diff(d["rang"])) + 1
    for groupe in np.split(np.arange(len(d["rang"])), frontieres):
        if len(groupe) == 0:
            continue
        identifiant = str(d["ids"][d["rang"][groupe[0]]])
        positions = list(zip(d["debut"][groupe].tolist(), d["fin"][groupe].tolist()))
        cache[identifiant] = (positions, d["vecteurs"][groupe].astype(np.float32))
    return cache


def enregistrer(cache):
    ids = list(cache)
    rang, debut, fin, vecteurs = [], [], [], []
    for i, identifiant in enumerate(ids):
        positions, vec = cache[identifiant]
        rang += [i] * len(positions)
        debut += [d for d, _ in positions]
        fin += [f for _, f in positions]
        vecteurs.append(vec)
    FICHIER_PHRASES.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        FICHIER_PHRASES,
        ids=np.array(ids), rang=np.array(rang), debut=np.array(debut), fin=np.array(fin),
        # float16 : deux fois moins de place, sans effet visible sur le choix de la phrase
        vecteurs=np.concatenate(vecteurs).astype(np.float16),
    )


def precalculer(morceaux, vectoriser, prefixe):
    """Vectorise les phrases des morceaux qui n'en ont pas encore. Incremental."""
    cache = charger()
    connus = {m["id"] for m in morceaux}
    for identifiant in list(cache):
        if identifiant not in connus:
            del cache[identifiant]          # morceau disparu du corpus

    a_faire = [m for m in morceaux if m["id"] not in cache]
    if not a_faire:
        print("phrases deja vectorisees - rien a faire")
        return

    positions = [phrases_avec_positions(m["texte"]) for m in a_faire]
    textes = [m["texte"][d:f] for m, pos in zip(a_faire, positions) for d, f in pos]
    print(f"vectorisation de {len(textes)} phrases ({len(a_faire)} morceaux)...")
    vecteurs = np.array(vectoriser(textes, prefixe), dtype=np.float32)

    i = 0
    for m, pos in zip(a_faire, positions):
        cache[m["id"]] = (pos, vecteurs[i:i + len(pos)])
        i += len(pos)
    enregistrer(cache)
    print(f"{sum(len(p) for p, _ in cache.values())} phrases dans {FICHIER_PHRASES}")
