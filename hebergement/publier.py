"""Publie la version en ligne sur Hugging Face Spaces (Space statique, gratuit).

Prealables : site construit (hebergement.exporter) et connexion faite une fois avec
    .venv\\Scripts\\hf auth login

Usage (dossier du projet) :
    .venv\\Scripts\\python -m hebergement.exporter
    .venv\\Scripts\\python -m hebergement.publier
"""
import sys

from huggingface_hub import HfApi

from hebergement.exporter import DOSSIER_SITE

NOM_DU_SPACE = "recueil-de-conformite"


def main():
    if not (DOSSIER_SITE / "index.html").exists():
        sys.exit("site absent : lancer d'abord python -m hebergement.exporter")

    api = HfApi()
    compte = api.whoami()["name"]
    depot = f"{compte}/{NOM_DU_SPACE}"

    api.create_repo(depot, repo_type="space", space_sdk="static", exist_ok=True)
    api.upload_folder(repo_id=depot, repo_type="space", folder_path=DOSSIER_SITE,
                      commit_message="Mise a jour du site")
    print("\nPublie :")
    print(f"  https://huggingface.co/spaces/{depot}")
    print(f"  https://{compte.lower()}-{NOM_DU_SPACE}.static.hf.space   (lien direct)")


if __name__ == "__main__":
    main()
