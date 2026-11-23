"""Etape 2a - transforme chaque morceau en vecteur et range le tout dans ChromaDB.

Un vecteur (embedding) est une liste de nombres qui represente le sens d'un texte.
Deux textes qui parlent de la meme chose ont des vecteurs proches, meme sans mots communs.
"""
import hashlib
import json
import pathlib
import shutil
import sys

import chromadb

from conformite import phrases

from conformite.chemins import DOSSIER_DB, FICHIER_MORCEAUX
COLLECTION = "conformite"

# Modele multilingue : indispensable, nos textes sont en francais.
# Variante plus rapide et plus legere si besoin : intfloat/multilingual-e5-small
MODELE = "intfloat/multilingual-e5-base"

# La famille e5 exige ces prefixes : "passage: " pour les documents, "query: " pour
# les questions. Sans eux, la qualite de la recherche chute nettement.
PREFIXE_PASSAGE = "passage: "
PREFIXE_REQUETE = "query: "

# Champs recopies comme etiquettes dans ChromaDB : ce sont eux qui permettront de filtrer
CHAMPS_METADONNEES = [
    "source_id", "source_titre", "nature", "autorite", "juridiction", "date",
    "url", "version", "type_unite", "numero", "paragraphe", "partie",
    "titre_unite", "chapitre", "section", "reference", "nb_caracteres", "ordre",
]


def charger_morceaux():
    if not FICHIER_MORCEAUX.exists():
        raise SystemExit(f"{FICHIER_MORCEAUX} absent - lance d'abord python -m conformite.decoupage")
    with FICHIER_MORCEAUX.open(encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f if ligne.strip()]


def charger_modele():
    """Importe sentence-transformers au dernier moment : l'import est lent."""
    from sentence_transformers import SentenceTransformer

    print(f"chargement du modele {MODELE} (premiere fois : telechargement ~1 Go)")
    return SentenceTransformer(MODELE)


def fabrique_vectoriseur(modele):
    def vectoriser(textes, prefixe):
        return modele.encode(
            [prefixe + t for t in textes],
            batch_size=32,
            normalize_embeddings=True,   # vecteurs de longueur 1 : la similarite cosinus devient un simple produit
            show_progress_bar=True,
        ).tolist()

    return vectoriser


def nettoyer_metadonnees(morceau):
    """ChromaDB n'accepte que str, int, float, bool. Pas de None, pas de liste."""
    propre = {}
    for champ in CHAMPS_METADONNEES:
        valeur = morceau.get(champ)
        if valeur is None or valeur == "":
            continue
        propre[champ] = valeur if isinstance(valeur, (int, float, bool)) else str(valeur)
    return propre


def empreinte(morceau):
    """Resume court du texte vectorise : s'il change, le morceau doit etre revectorise."""
    return hashlib.sha1(morceau["texte_indexe"].encode("utf-8")).hexdigest()[:16]


def construire(morceaux, vectoriser, remettre_a_zero=False):
    """Indexation incrementale : seuls les morceaux nouveaux ou modifies sont vectorises.

    Vectoriser tout le corpus prend plus de 20 minutes sur processeur. Ajouter une source
    ou corriger un article ne doit couter que le temps des morceaux concernes.
    """
    if remettre_a_zero and DOSSIER_DB.exists():
        shutil.rmtree(DOSSIER_DB)
        print("base precedente supprimee")

    DOSSIER_DB.parent.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(DOSSIER_DB))
    collection = client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},   # on compare les vecteurs par angle, pas par distance brute
    )

    existants = collection.get(include=["metadatas"])
    empreinte_en_base = {i: (m or {}).get("empreinte") for i, m in zip(existants["ids"], existants["metadatas"])}
    voulus = {m["id"]: m for m in morceaux}

    # 1. Morceaux disparus du corpus : retires de la base
    obsoletes = [i for i in empreinte_en_base if i not in voulus]
    if obsoletes:
        collection.delete(ids=obsoletes)
        print(f"{len(obsoletes)} morceaux obsoletes retires")

    # 2. Morceaux deja la sans empreinte (base faite avant son ajout) : on ajoute l'empreinte
    #    sans revectoriser. Pour forcer une revectorisation complete : --reset
    sans_empreinte = [voulus[i] for i, e in empreinte_en_base.items() if i in voulus and e is None]
    if sans_empreinte:
        collection.update(
            ids=[m["id"] for m in sans_empreinte],
            metadatas=[nettoyer_metadonnees(m) | {"empreinte": empreinte(m)} for m in sans_empreinte],
        )
        print(f"{len(sans_empreinte)} morceaux existants marques de leur empreinte")
        for m in sans_empreinte:
            empreinte_en_base[m["id"]] = empreinte(m)

    # 3. Morceaux nouveaux ou dont le texte a change : vectorises
    a_faire = [m for m in morceaux if empreinte_en_base.get(m["id"]) != empreinte(m)]
    if not a_faire:
        print(f"base deja a jour ({collection.count()} morceaux) - rien a vectoriser")
        return collection

    print(f"vectorisation de {len(a_faire)} morceaux nouveaux ou modifies "
          f"(sur {len(morceaux)})...")
    vecteurs = vectoriser([m["texte_indexe"] for m in a_faire], PREFIXE_PASSAGE)

    print("ecriture dans ChromaDB...")
    lot = 500
    for debut in range(0, len(a_faire), lot):
        tranche = a_faire[debut:debut + lot]
        collection.upsert(
            ids=[m["id"] for m in tranche],
            embeddings=vecteurs[debut:debut + lot],
            documents=[m["texte"] for m in tranche],          # ce qui sera affiche
            metadatas=[nettoyer_metadonnees(m) | {"empreinte": empreinte(m)} for m in tranche],
        )
        print(f"  {min(debut + lot, len(a_faire))}/{len(a_faire)}")

    print(f"\n{collection.count()} morceaux dans la collection '{COLLECTION}'")
    return collection


def main():
    remettre_a_zero = "--reset" in sys.argv
    morceaux = charger_morceaux()
    print(f"{len(morceaux)} morceaux lus dans {FICHIER_MORCEAUX}")

    repartition = {}
    for m in morceaux:
        cle = f"{m['source_id']}/{m['nature']}"
        repartition[cle] = repartition.get(cle, 0) + 1
    print(f"repartition : {repartition}\n")

    modele = charger_modele()
    vectoriser = fabrique_vectoriseur(modele)
    collection = construire(morceaux, vectoriser, remettre_a_zero)

    # Phrases de chaque morceau, vectorisees d'avance pour un surlignage instantane.
    # Facultatif : environ 6000 phrases, pres d'une heure sur processeur. Sans cette etape,
    # l'application les vectorise a la demande et les garde pour la fois suivante.
    if remettre_a_zero and phrases.FICHIER_PHRASES.exists():
        phrases.FICHIER_PHRASES.unlink()
    if "--phrases" in sys.argv:
        phrases.precalculer(morceaux, vectoriser, PREFIXE_PASSAGE)

    print("\nverification : un echantillon tire de la base")
    extrait = collection.get(limit=2, include=["metadatas", "documents"])
    for identifiant, meta in zip(extrait["ids"], extrait["metadatas"]):
        print(f"  {identifiant} | nature={meta.get('nature')} | {meta.get('reference', '')[:70]}")


if __name__ == "__main__":
    main()
