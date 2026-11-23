"""Etape 1a - telecharge chaque source et la garde telle quelle sur le disque.

But : ne jamais redescendre un texte deux fois. On garde le brut, on retraite autant qu'on veut.
"""
import json
import pathlib

import requests

from conformite.chemins import DOSSIER_BRUT, FICHIER_SOURCES
EN_TETES = {"User-Agent": "projet-etudiant-rag-conformite/1.0"}
URL_CELLAR = "https://publications.europa.eu/resource/celex/"


def telecharger(source, forcer=False):
    cible = DOSSIER_BRUT / f"{source['id']}.{source['format']}"

    if cible.exists() and not forcer:
        print(f"  deja la : {cible} ({cible.stat().st_size // 1024} Ko)")
        return cible

    print(f"  telechargement de {source['id']}...")
    if source.get("celex"):
        # Le site EUR-Lex oppose desormais un defi anti-robot aux scripts (reponse 202 vide).
        # Le depot Cellar de l'Office des publications est l'acces prevu pour les programmes :
        # meme texte officiel, obtenu par son numero CELEX.
        reponse = requests.get(
            URL_CELLAR + source["celex"],
            headers={**EN_TETES, "Accept": "text/html, application/xhtml+xml;q=0.9", "Accept-Language": "fra"},
            timeout=120,
        )
    else:
        reponse = requests.get(source["url"], headers=EN_TETES, timeout=120)
    reponse.raise_for_status()
    # raise_for_status ne voit que les erreurs (4xx, 5xx) : un 202 vide passerait sans bruit
    if reponse.status_code != 200 or not reponse.content:
        raise RuntimeError(f"reponse inattendue {reponse.status_code}, {len(reponse.content)} octets")

    if source["format"] == "html":
        reponse.encoding = reponse.apparent_encoding or "utf-8"
        cible.write_text(reponse.text, encoding="utf-8")
    else:
        cible.write_bytes(reponse.content)

    print(f"  ecrit : {cible} ({cible.stat().st_size // 1024} Ko)")
    return cible


def main():
    DOSSIER_BRUT.mkdir(parents=True, exist_ok=True)
    sources = json.loads(FICHIER_SOURCES.read_text(encoding="utf-8"))

    for source in sources:
        print(f"\n{source['titre']}")
        try:
            telecharger(source)
        except Exception as erreur:
            print(f"  ECHEC : {erreur}")

    print(f"\nTermine. Fichiers dans {DOSSIER_BRUT}/")


if __name__ == "__main__":
    main()
