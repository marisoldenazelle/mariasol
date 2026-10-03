@echo off
REM ---------------------------------------------------------------------------
REM Demarrage de mariasol — Windows.
REM
REM Trois defauts constates en deploiement sont traites ici, et il vaut mieux
REM savoir pourquoi ces lignes existent avant de les simplifier :
REM
REM  1. « pushd » et non « cd /d » : depuis un lecteur reseau (\\serveur\part),
REM     cmd.exe refuse un chemin UNC comme repertoire courant, retombe dans
REM     C:\Windows et la suite s'execute au mauvais endroit. « pushd » monte un
REM     lecteur temporaire pour l'occasion.
REM  2. Windows 10 et 11 livrent un faux « python.exe » dans WindowsApps : il
REM     est dans le PATH meme sans Python installe, et ouvre le Microsoft Store.
REM     « where python » ne suffit donc pas, on execute Python pour de bon.
REM  3. Si « pip install » echoue (pas d'acces au depot PyPI), le dossier .venv
REM     existe mais reste vide — et tous les lancements suivants sautaient
REM     l'installation. L'application ne demarrait plus jamais, sans message.
REM     On verifie donc le code de retour et on efface l'environnement rate.
REM ---------------------------------------------------------------------------
setlocal
pushd "%~dp0"

if not exist app.py (
  echo Ce script doit rester dans le dossier de l'application, a cote de app.py.
  pause
  popd
  exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 ou plus recent est introuvable sur ce poste.
  echo.
  echo Installez-le depuis https://www.python.org/downloads/
  echo IMPORTANT : cochez "Add Python to PATH" pendant l'installation.
  echo.
  echo Si Python est deja installe, c'est que le raccourci du Microsoft Store
  echo masque la vraie installation : Parametres ^> Applications ^>
  echo Alias d'execution d'applications, et decochez python.exe.
  pause
  popd
  exit /b 1
)

if not exist .venv\Scripts\streamlit.exe (
  if exist .venv (
    echo Installation precedente incomplete — on repart de zero.
    rmdir /s /q .venv
  )
  echo Premiere installation - cela prend deux a trois minutes...
  python -m venv .venv
  if errorlevel 1 goto :echec_venv

  REM Les dependances sont d'abord cherchees dans le dossier "wheelhouse" s'il
  REM a ete livre avec l'application : c'est le chemin d'installation sur un
  REM reseau sans acces a PyPI. Sinon, on passe par le reseau.
  if exist wheelhouse (
    echo Installation depuis le dossier wheelhouse, sans acces reseau...
    .venv\Scripts\python.exe -m pip install --no-index --find-links wheelhouse -r requirements.txt
  ) else (
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt
  )
  if errorlevel 1 goto :echec_pip
  if not exist .venv\Scripts\streamlit.exe goto :echec_pip
  echo Installation terminee.
)

echo Demarrage - l'application s'ouvre dans votre navigateur.
echo Si elle ne s'ouvre pas, allez a l'adresse affichee ci-dessous.
echo Pour l'arreter : Ctrl+C dans cette fenetre.
.venv\Scripts\streamlit.exe run app.py --server.address localhost --server.headless false
popd
endlocal
exit /b 0

:echec_venv
echo.
echo La creation de l'environnement Python a echoue.
echo Verifiez que vous avez le droit d'ecrire dans ce dossier.
pause
popd
exit /b 1

:echec_pip
echo.
echo L'installation des dependances a echoue — le message ci-dessus dit
echo pourquoi. Cas le plus frequent : ce poste n'a pas acces au depot PyPI.
echo.
echo Deux solutions :
echo  - demander au service informatique l'adresse du miroir interne, puis
echo    relancer avec : .venv\Scripts\python.exe -m pip install -i ADRESSE -r requirements.txt
echo  - ou faire preparer le dossier "wheelhouse" sur un poste connecte
echo    (python -m pip download -r requirements.txt -d wheelhouse) et le
echo    copier ici avant de relancer ce script.
echo.
echo Le dossier .venv incomplet a ete conserve pour diagnostic : supprimez-le
echo avant la prochaine tentative.
pause
popd
exit /b 1
