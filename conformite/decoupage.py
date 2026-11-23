"""Etape 1b - transforme un texte brut en morceaux, un par article, avec ses etiquettes.

Pourquoi par article et pas tous les 1000 caracteres : un article est une unite de sens
complete, et son numero donne une citation exacte dans la reponse.
"""
import json
import pathlib
import re
import sys

from bs4 import BeautifulSoup

from conformite.chemins import DOSSIER_BRUT, FICHIER_MORCEAUX as FICHIER_SORTIE, FICHIER_SOURCES

# Le texte consolide d'EUR-Lex est parseme de marqueurs de modification : ►B ►M1 ►C2 ◄
MARQUEURS = re.compile(r"[►◄▼▲]\s*[BMCA]?\d*")

RE_CHAPITRE = re.compile(r"^CHAPITRE\s+([IVXLC]+)\b(.*)$")
RE_SECTION = re.compile(r"^Section\s+(\d+)\b(.*)$")
RE_ANNEXE = re.compile(r"^ANNEXE\s+([IVXLC]+|\d+)?\b(.*)$")
# "Article premier" en francais, et pas "Article 1" : piege classique du texte d'EUR-Lex
RE_ARTICLE = re.compile(r"^Article\s+(premier|\d+(?:\s(?:bis|ter|quater))?)\b(.*)$")
RE_CONSIDERANT = re.compile(r"^\((\d{1,3})\)\s*(.*)$")
# Debut de paragraphe numerote : "1." dans les articles, "1)" dans les articles de definitions.
# Sur EUR-Lex, le numero est souvent seul sur sa ligne ("8)" puis la definition a la ligne
# suivante) : le texte apres le numero est donc facultatif.
RE_PARAGRAPHE = re.compile(r"^(\d{1,2})[.)](?:\s+(.*))?$")
# Fin de phrase, pour le decoupage de dernier recours
RE_FIN_PHRASE = re.compile(r"(?<=[.;:!?])\s+")
# Au-dela de cette taille, un article est sous-decoupe par paragraphe
SEUIL_SOUS_DECOUPAGE = 2500


def lignes_propres(chemin):
    """HTML -> liste de lignes de texte nettoyees."""
    if chemin.suffix == ".html":
        soupe = BeautifulSoup(chemin.read_text(encoding="utf-8"), "html.parser")
        for balise in soupe(["script", "style"]):
            balise.decompose()
        texte = soupe.get_text("\n")
    else:
        texte = chemin.read_text(encoding="utf-8")

    texte = texte.replace("\xa0", " ")
    lignes = []
    for ligne in texte.split("\n"):
        ligne = MARQUEURS.sub("", ligne)
        ligne = re.sub(r"[ \t]+", " ", ligne).strip()
        if ligne:
            lignes.append(ligne)
    return lignes


def numero_lisible(brut):
    return "1" if brut.startswith("premier") else brut.strip()


def decouper(lignes):
    """Parcourt les lignes et ferme un morceau des qu'un nouvel en-tete apparait."""
    morceaux = []
    courant = None
    chapitre = section = None
    dans_preambule = True

    def fermer():
        if courant and courant["corps"]:
            courant["texte"] = "\n".join(courant.pop("corps")).strip()
            if courant["texte"]:
                morceaux.append(courant)

    for ligne in lignes:
        if m := RE_CHAPITRE.match(ligne):
            fermer()
            courant = None
            dans_preambule = False
            chapitre, section = ligne, None
            continue

        if m := RE_SECTION.match(ligne):
            fermer()
            courant = None
            section = ligne
            continue

        if m := RE_ARTICLE.match(ligne):
            fermer()
            dans_preambule = False
            courant = {
                "type_unite": "article",
                "numero": numero_lisible(m.group(1)),
                "titre_unite": m.group(2).strip(),
                "chapitre": chapitre,
                "section": section,
                "corps": [],
            }
            continue

        if m := RE_ANNEXE.match(ligne):
            fermer()
            chapitre = section = None
            courant = {
                "type_unite": "annexe",
                "numero": (m.group(1) or "").strip(),
                "titre_unite": m.group(2).strip(),
                "chapitre": None,
                "section": None,
                "corps": [],
            }
            continue

        # Avant le premier article : les considerants du preambule, un morceau chacun
        if dans_preambule:
            if m := RE_CONSIDERANT.match(ligne):
                fermer()
                courant = {
                    "type_unite": "considerant",
                    "numero": m.group(1),
                    "titre_unite": "",
                    "chapitre": None,
                    "section": None,
                    "corps": [m.group(2)] if m.group(2) else [],
                }
                continue
            if courant is None:
                continue

        if courant is None:
            continue

        # "Article 14" puis "bis" sur la ligne suivante (version consolidee d'EUR-Lex) :
        # "bis" fait partie du numero, ce n'est pas le titre
        if (courant["type_unite"] == "article" and not courant["titre_unite"] and not courant["corps"]
                and ligne in ("bis", "ter", "quater")):
            courant["numero"] += f" {ligne}"
            continue

        # Un titre d'article vide se remplit avec la premiere ligne rencontree
        if courant["type_unite"] in ("article", "annexe") and not courant["titre_unite"] and not courant["corps"]:
            courant["titre_unite"] = ligne
            continue

        courant["corps"].append(ligne)

    fermer()
    return morceaux


def par_paragraphe(texte):
    """Niveau 1 : coupe aux debuts de paragraphes numerotes."""
    blocs = []
    numero_courant = ""
    tampon = []

    for ligne in texte.split("\n"):
        if m := RE_PARAGRAPHE.match(ligne):
            if tampon:
                blocs.append((numero_courant, "\n".join(tampon).strip()))
            numero_courant = m.group(1)
            tampon = [ligne]
        else:
            tampon.append(ligne)

    if tampon:
        blocs.append((numero_courant, "\n".join(tampon).strip()))

    blocs = [(n, t) for n, t in blocs if t]
    return blocs if len(blocs) > 1 else [("", texte)]


def par_phrases(texte, cible=1800):
    """Niveau 2 : dernier recours pour un bloc sans structure. Regroupe des phrases entieres."""
    phrases = RE_FIN_PHRASE.split(texte)
    parties = []
    tampon = ""

    for phrase in phrases:
        if tampon and len(tampon) + len(phrase) + 1 > cible:
            parties.append(tampon.strip())
            tampon = phrase
        else:
            tampon = f"{tampon} {phrase}".strip()

    if tampon.strip():
        parties.append(tampon.strip())
    return parties or [texte]


def sous_decouper(texte):
    """Renvoie une liste de (paragraphe, partie, texte). Chaine vide = niveau non utilise."""
    if len(texte) <= SEUIL_SOUS_DECOUPAGE:
        return [("", "", texte)]

    resultat = []
    for numero, bloc in par_paragraphe(texte):
        if len(bloc) <= SEUIL_SOUS_DECOUPAGE:
            resultat.append((numero, "", bloc))
            continue
        parties = par_phrases(bloc)
        if len(parties) == 1:
            resultat.append((numero, "", bloc))
        else:
            for i, partie in enumerate(parties, 1):
                resultat.append((numero, str(i), partie))
    return resultat


def reference(source, morceau, paragraphe, partie):
    """La phrase d'en-tete qui situe le morceau. Elle part dans le vecteur avec le texte."""
    libelle = {"article": "Article", "annexe": "Annexe", "considerant": "Considerant"}
    bouts = [source["titre"], f"{libelle[morceau['type_unite']]} {morceau['numero']}".strip()]
    if paragraphe:
        bouts.append(f"paragraphe {paragraphe}")
    if partie:
        bouts.append(f"extrait {partie}")
    if morceau["titre_unite"]:
        bouts.append(morceau["titre_unite"])
    return " — ".join(bouts)


def traiter(source):
    chemin = DOSSIER_BRUT / f"{source['id']}.{source['format']}"
    if not chemin.exists():
        print(f"  manquant : {chemin} - lance d'abord python -m conformite.collecte")
        return []

    morceaux = decouper(lignes_propres(chemin))

    enrichis = []
    deja_vus = {}
    for morceau in morceaux:
        # "14 bis" -> "14-bis" : pas d'espace dans un identifiant
        etiquette = f"{morceau['type_unite']}-{morceau['numero']}".strip("-").replace(" ", "-")
        for paragraphe, partie, texte in sous_decouper(morceau["texte"]):
            identifiant = f"{source['id']}-{etiquette}"
            if paragraphe:
                identifiant += f"-par-{paragraphe}"
            if partie:
                identifiant += f"-p{partie}"
            # Une annexe en sections A, B, C renumerote ses paragraphes a partir de 1 :
            # le meme identifiant reviendrait. La base exige des identifiants uniques.
            deja_vus[identifiant] = deja_vus.get(identifiant, 0) + 1
            if deja_vus[identifiant] > 1:
                identifiant += f"-occ{deja_vus[identifiant]}"
            en_tete = reference(source, morceau, paragraphe, partie)
            enrichis.append({
            "id": identifiant,
            # rang dans le texte d'origine : pour reconstituer un article dans le bon ordre
            "ordre": len(enrichis),
            "texte": texte,
            # ce qui part dans le vecteur : l'en-tete donne le contexte au morceau
            "texte_indexe": f"{en_tete}\n{texte}",
            "reference": en_tete,
            "paragraphe": paragraphe,
            "partie": partie,
            "source_id": source["id"],
            "source_titre": source["titre"],
            # les trois etiquettes qui font la valeur du projet
            "nature": source["nature"],
            "autorite": source["autorite"],
            "juridiction": source["juridiction"],
            "date": source["date"],
            "url": source["url"],
            "type_unite": morceau["type_unite"],
            "numero": morceau["numero"],
            "titre_unite": morceau["titre_unite"],
            "chapitre": morceau["chapitre"],
            "section": morceau["section"],
            "version": source.get("version", ""),
            "nb_caracteres": len(texte),
            })
    return enrichis


def main():
    global DOSSIER_BRUT, FICHIER_SORTIE
    fichier = sys.argv[1] if len(sys.argv) > 1 else str(FICHIER_SOURCES)
    sources = json.loads(pathlib.Path(fichier).read_text(encoding="utf-8"))
    tous = []

    # Un fichier de sources de test lit ses textes a cote de lui et ecrit a cote de lui :
    # sinon le test ecraserait data/morceaux.jsonl, le vrai resultat.
    if pathlib.Path(fichier).resolve() != FICHIER_SOURCES:
        DOSSIER_BRUT = pathlib.Path(fichier).parent
        FICHIER_SORTIE = DOSSIER_BRUT / "morceaux_test.jsonl"

    for source in sources:
        print(f"\n{source['titre']}")
        morceaux = traiter(source)
        par_type = {}
        for m in morceaux:
            par_type[m["type_unite"]] = par_type.get(m["type_unite"], 0) + 1
        print(f"  {len(morceaux)} morceaux : {par_type}")
        if morceaux:
            articles = [m for m in morceaux if m["type_unite"] == "article"]
            if articles:
                print(f"  premier article : {articles[0]['numero']} - {articles[0]['titre_unite'][:60]}")
                print(f"  dernier article : {articles[-1]['numero']} - {articles[-1]['titre_unite'][:60]}")
                tailles = sorted(m["nb_caracteres"] for m in articles)
                print(f"  taille des morceaux d'article : min {tailles[0]}, median {tailles[len(tailles)//2]}, max {tailles[-1]}")
                sous_decoupes = len({m["numero"] for m in articles if m["paragraphe"] or m["partie"]})
                print(f"  articles sous-decoupes : {sous_decoupes}")
            tailles_tout = sorted(m["nb_caracteres"] for m in morceaux)
            print(f"  tous morceaux : min {tailles_tout[0]}, median {tailles_tout[len(tailles_tout)//2]}, max {tailles_tout[-1]}")
            trop_gros = [m["id"] for m in morceaux if m["nb_caracteres"] > SEUIL_SOUS_DECOUPAGE]
            print(f"  morceaux encore > {SEUIL_SOUS_DECOUPAGE} : {len(trop_gros)}")
            if trop_gros:
                print(f"    a surveiller : {', '.join(trop_gros[:5])}")
        tous.extend(morceaux)

    FICHIER_SORTIE.parent.mkdir(parents=True, exist_ok=True)
    with FICHIER_SORTIE.open("w", encoding="utf-8") as f:
        for morceau in tous:
            f.write(json.dumps(morceau, ensure_ascii=False) + "\n")

    print(f"\n{len(tous)} morceaux ecrits dans {FICHIER_SORTIE}")


if __name__ == "__main__":
    main()
