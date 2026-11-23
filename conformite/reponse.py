"""Etape 3 - redige une reponse a partir des seuls passages retrouves.

Le modele de langage ne "sait" rien ici : on lui donne les passages, il les reformule et
les cite. S'il n'y a pas de cle d'API, on renvoie quand meme les passages (mode consultation).

Usage (dossier du projet, terminal PowerShell) :
    .venv\\Scripts\\python -m conformite.reponse "Quelles informations donner a la personne concernee ?"

Cles attendues dans un fichier .env a la racine (jamais committe) :
    MISTRAL_API_KEY=...
    OPENAI_API_KEY=...      (facultatif, repli)
"""
import json
import os
import sys

import httpx
from dotenv import load_dotenv

from conformite.chemins import FICHIER_ENV
from conformite.recherche import Recherche

load_dotenv(FICHIER_ENV)

# Mistral et OpenAI exposent la meme forme d'API "chat completions" :
# une seule fonction d'appel suffit, seuls l'adresse, la cle et le modele changent.
FOURNISSEURS = [
    {"nom": "mistral", "url": "https://api.mistral.ai/v1/chat/completions",
     "cle": "MISTRAL_API_KEY", "modele": "mistral-small-latest"},
    {"nom": "openai", "url": "https://api.openai.com/v1/chat/completions",
     "cle": "OPENAI_API_KEY", "modele": "gpt-4o-mini"},
]

LIBELLE_NATURE = {
    "contraignant": "obligation legale (texte contraignant)",
    "recommandation": "recommandation d'autorite (non contraignante)",
    "ethique": "cadre ethique (non contraignant)",
}

CONSIGNES = """Tu aides a s'orienter dans des textes de conformite (RGPD, AI Act, recommandations CNIL).

Regles strictes :
1. Reponds UNIQUEMENT a partir des passages fournis. N'utilise aucune connaissance exterieure.
2. Chaque affirmation cite sa source entre crochets, par son numero : [1], [2]...
3. Pour chaque source citee, precise sa nature : obligation legale, recommandation ou cadre ethique.
4. Si les passages ne permettent pas de repondre, ecris exactement : "Je ne sais pas : les textes fournis ne tranchent pas cette question." puis indique quels passages s'en approchent le plus.
5. Tu orientes dans les textes, tu ne qualifies rien juridiquement. Ne dis jamais qu'un systeme EST a haut risque ou qu'un traitement EST licite : montre les articles qui en definissent les criteres.
6. Reponds en francais, de facon concise (moins de 250 mots)."""


def bloc_passages(passages):
    """Numerote les passages pour que le modele puisse les citer par [n]."""
    lignes = []
    for i, p in enumerate(passages, 1):
        nature = LIBELLE_NATURE.get(p["nature"], p["nature"])
        lignes.append(f"[{i}] {p['reference']}\nNature : {nature}\n{p['texte']}")
    return "\n\n".join(lignes)


def construire_messages(question, passages):
    return [
        {"role": "system", "content": CONSIGNES},
        {"role": "user", "content": f"Passages :\n\n{bloc_passages(passages)}\n\nQuestion : {question}"},
    ]


def appeler_modele(messages):
    """Essaie chaque fournisseur dans l'ordre. Renvoie (texte, nom) ou (None, None)."""
    for f in FOURNISSEURS:
        cle = os.getenv(f["cle"])
        if not cle:
            continue
        try:
            reponse = httpx.post(
                f["url"],
                headers={"Authorization": f"Bearer {cle}"},
                # temperature basse : on veut une reformulation fidele, pas de la creativite
                json={"model": f["modele"], "messages": messages, "temperature": 0.1},
                timeout=60,
            )
            reponse.raise_for_status()
            return reponse.json()["choices"][0]["message"]["content"], f["nom"]
        except Exception as erreur:
            print(f"  echec {f['nom']} : {erreur}", file=sys.stderr)
    return None, None


def redaction_disponible():
    return any(os.getenv(f["cle"]) for f in FOURNISSEURS)


def appeler_modele_en_flux(messages):
    """Comme appeler_modele, mais renvoie le texte au fur et a mesure qu'il est ecrit.

    Le premier mot arrive en moins d'une seconde, au lieu d'attendre la reponse entiere
    (plusieurs secondes) : c'est le temps de reponse ressenti qui compte pour l'utilisateur.
    Le format est celui des "server-sent events" : des lignes "data: {...}".
    """
    for f in FOURNISSEURS:
        cle = os.getenv(f["cle"])
        if not cle:
            continue
        deja_envoye = False
        try:
            with httpx.stream(
                "POST", f["url"],
                headers={"Authorization": f"Bearer {cle}"},
                json={"model": f["modele"], "messages": messages, "temperature": 0.1, "stream": True},
                timeout=60,
            ) as reponse:
                reponse.raise_for_status()
                for ligne in reponse.iter_lines():
                    if not ligne.startswith("data: ") or ligne == "data: [DONE]":
                        continue
                    morceau = json.loads(ligne[6:])["choices"][0]["delta"].get("content")
                    if morceau:
                        deja_envoye = True
                        yield morceau
            return
        except Exception as erreur:
            print(f"  echec {f['nom']} : {erreur}", file=sys.stderr)
            # Si du texte est deja parti, on ne peut pas recommencer avec un autre fournisseur
            if deja_envoye:
                yield "\n\n[reponse interrompue]"
                return


def repondre(recherche, question, k=5, **filtres):
    passages = recherche.rechercher(question, k=k, **filtres)
    if not passages:
        return {"reponse": None, "fournisseur": None, "passages": []}
    texte, fournisseur = appeler_modele(construire_messages(question, passages))
    return {"reponse": texte, "fournisseur": fournisseur, "passages": passages}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        raise SystemExit('usage : python -m conformite.reponse "ta question"')
    question = " ".join(sys.argv[1:])

    resultat = repondre(Recherche(), question)
    print(f"Question : {question}\n")
    if resultat["reponse"]:
        print(f"Reponse ({resultat['fournisseur']}) :\n{resultat['reponse']}\n")
    else:
        print("Pas de cle d'API (ou appel en echec) : voici seulement les passages.\n")
    print("Sources :")
    for i, p in enumerate(resultat["passages"], 1):
        print(f"  [{i}] {p['reference']} ({p['nature']}, score {p['score']:.3f})")


if __name__ == "__main__":
    main()
