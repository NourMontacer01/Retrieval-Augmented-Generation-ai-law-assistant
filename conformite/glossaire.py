"""Glossaire : traduit les sigles et le langage courant dans le vocabulaire des textes.

Probleme : l'utilisateur ecrit "AIPD", "DPO" ou "cookie" ; le reglement ecrit "analyse
d'impact relative a la protection des donnees", "delegue a la protection des donnees",
"informations stockees dans l'equipement terminal". Ni les vecteurs ni les mots-cles ne
font ce lien de facon fiable. On ajoute donc a la question la formulation du texte.

Regle de redaction : uniquement des equivalences juridiques generales (sigles officiels,
termes consacres), jamais une entree ecrite pour faire reussir une question de test precise.
"""
import re
import unicodedata

# cle : expression cherchee dans la question (sans accents, en minuscules)
# valeur : formulation des textes ajoutee a la question
GLOSSAIRE = {
    # sigles du RGPD
    "aipd": "analyse d'impact relative a la protection des donnees",
    "dpia": "analyse d'impact relative a la protection des donnees",
    "dpo": "delegue a la protection des donnees",
    "dpd": "delegue a la protection des donnees",
    "cnil": "autorite de controle",
    "edpb": "comite europeen de la protection des donnees",
    "cepd": "comite europeen de la protection des donnees",
    "rgpd": "reglement (UE) 2016/679",
    # sigles de l'AI Act
    "gpai": "modele d'IA a usage general",
    "llm": "modele d'IA a usage general",
    "sia": "systeme d'IA",
    # langage courant -> terme juridique
    "fuite de donnees": "violation de donnees a caractere personnel",
    "fuite": "violation de donnees a caractere personnel",
    "piratage": "violation de donnees a caractere personnel",
    "pirate": "violation de donnees a caractere personnel",
    "hack": "violation de donnees a caractere personnel",
    "cookie": "stockage d'informations ou acces a des informations stockees dans l'equipement terminal",
    "traceur": "stockage d'informations ou acces a des informations stockees dans l'equipement terminal",
    "droit a l'oubli": "droit a l'effacement",
    "supprimer mes donnees": "droit a l'effacement",
    "reconnaissance faciale": "identification biometrique a distance",
    "algorithme": "decision fondee exclusivement sur un traitement automatise",
    "amende": "amendes administratives sanctions",
    "entreprise": "responsable du traitement",
    "prestataire": "sous-traitant",
    "prevenir": "notification communication",
    # forme de la question -> partie du texte qui y repond
    "depuis quand": "entree en vigueur et application, est applicable a partir du",
    "a partir de quand": "entree en vigueur et application, est applicable a partir du",
    "date d'application": "entree en vigueur et application, est applicable a partir du",
    "qu'est-ce qu": "definitions, aux fins du present reglement on entend par",
    "difference entre": "definitions, aux fins du present reglement on entend par",
    "au sens de": "definitions, aux fins du present reglement on entend par",
    "definition": "definitions, aux fins du present reglement on entend par",
}

# Noms usuels des textes indexes -> identifiant de source (voir sources.json)
NOMS_DES_TEXTES = {
    "rgpd": "rgpd", "gdpr": "rgpd", "2016/679": "rgpd",
    "ai act": "ai-act", "reglement ia": "ai-act", "reglement sur l'ia": "ai-act", "2024/1689": "ai-act",
    "eprivacy": "eprivacy", "e-privacy": "eprivacy", "2002/58": "eprivacy",
    "data act": "data-act", "2023/2854": "data-act",
}

RE_ARTICLE = re.compile(r"\barticle\s+(\d+)(?:\s*(bis|ter))?\b")
RE_ANNEXE = re.compile(r"\bannexe\s+([ivxlc]+)\b")


def textes_nommes(question):
    """Les textes cites dans la question ("... de l'AI Act ?") -> ensemble d'identifiants."""
    q = sans_accents(question.lower())
    return {source for nom, source in NOMS_DES_TEXTES.items() if re.search(rf"\b{re.escape(nom)}\b", q)}


def references_explicites(question):
    """ "Que dit l'article 5 ?" -> [("article", "5")] ; "annexe III" -> [("annexe", "III")]."""
    q = sans_accents(question.lower())
    refs = [("article", f"{n} {suffixe}".strip()) for n, suffixe in RE_ARTICLE.findall(q)]
    refs += [("annexe", a.upper()) for a in RE_ANNEXE.findall(q)]
    return refs


def sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def enrichir(question):
    """Ajoute a la question les formulations des textes pour les termes reconnus."""
    q = sans_accents(question.lower())
    ajouts = []
    for terme, traduction in GLOSSAIRE.items():
        # \b : mot entier ("dpo" ne se declenche pas dans "adpo") ; e?s? : accords
        # du francais ("pirate", "piratee", "pirates")
        if re.search(rf"\b{re.escape(terme)}e?s?\b", q) and traduction not in ajouts:
            ajouts.append(traduction)
    return f"{question} ({'; '.join(ajouts)})" if ajouts else question
