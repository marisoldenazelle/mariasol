#!/usr/bin/env bash
# Démarrage de mariasol — macOS et Linux.
#
# Même précaution que la version Windows : un `pip install` qui échoue laissait
# un dossier .venv vide, et les lancements suivants sautaient l'installation —
# l'application ne démarrait plus jamais, sans message. On teste donc la
# présence de l'exécutable, pas celle du dossier, et on efface un environnement
# incomplet plutôt que de le garder.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f app.py ]; then
  echo "Ce script doit rester dans le dossier de l'application, à côté de app.py."
  exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)' 2>/dev/null; then
  echo "Python 3.10 ou plus récent est introuvable sur ce poste."
  echo "Installez-le depuis https://www.python.org/downloads/ puis relancez ce script."
  exit 1
fi

if [ ! -x .venv/bin/streamlit ]; then
  if [ -d .venv ]; then
    echo "Installation précédente incomplète — on repart de zéro."
    rm -rf .venv
  fi
  echo "Première installation — cela prend deux à trois minutes…"
  python3 -m venv .venv

  # Les dépendances sont d'abord cherchées dans « wheelhouse » s'il a été livré
  # avec l'application : c'est le chemin d'installation sur un réseau sans
  # accès à PyPI.
  if [ -d wheelhouse ]; then
    echo "Installation depuis le dossier wheelhouse, sans accès réseau…"
    install_ok=0
    ./.venv/bin/pip install --no-index --find-links wheelhouse -r requirements.txt || install_ok=1
  else
    install_ok=0
    ./.venv/bin/pip install --upgrade pip || install_ok=1
    ./.venv/bin/pip install -r requirements.txt || install_ok=1
  fi

  if [ "$install_ok" -ne 0 ] || [ ! -x .venv/bin/streamlit ]; then
    echo
    echo "L'installation des dépendances a échoué — le message ci-dessus dit"
    echo "pourquoi. Cas le plus fréquent : ce poste n'a pas accès au dépôt PyPI."
    echo "Préparez alors le dossier wheelhouse sur une machine connectée :"
    echo "  python3 -m pip download -r requirements.txt -d wheelhouse"
    echo "puis copiez-le ici et relancez ce script."
    exit 1
  fi
  echo "Installation terminée."
fi

echo "Démarrage — l'application s'ouvre dans votre navigateur."
echo "Si elle ne s'ouvre pas, allez à l'adresse affichée ci-dessous."
echo "Pour l'arrêter : Ctrl+C dans cette fenêtre."
exec ./.venv/bin/streamlit run app.py --server.address localhost --server.headless false
