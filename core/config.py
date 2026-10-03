"""Configuration centralisée, pilotée par variables d'environnement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # chargement optionnel d'un fichier .env
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

# Version affichée dans l'application : elle permet de savoir quelle archive
# tourne réellement, ce que les dates de fichiers ne disent pas.
__version__ = "1.5.3"
VERSION_DATE = "9 septembre 2026"

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CORPUS_DIR = DATA_DIR / "corpus"
RULES_DIR = DATA_DIR / "rules"
EXPORT_DIR = DATA_DIR / "exports"
for _d in (DATA_DIR, CORPUS_DIR, RULES_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    # --- Fournisseur LLM ---------------------------------------------------
    # albert  : API Albert de la DINUM (SecNumCloud) — défaut
    # openai_compatible : tout endpoint compatible OpenAI (LLM interne DGE, Ollama…)
    # offline : aucun appel réseau, extraction purement déterministe
    llm_provider: str = os.getenv("REGWATCH_LLM_PROVIDER", "albert")
    albert_base_url: str = os.getenv(
        "ALBERT_BASE_URL", "https://albert.api.etalab.gouv.fr/v1"
    )
    albert_api_key: str = os.getenv("ALBERT_API_KEY", "")
    llm_model: str = os.getenv("REGWATCH_LLM_MODEL", "mistral-small-3-2-24b-instruct-2506")
    llm_timeout: int = int(os.getenv("REGWATCH_LLM_TIMEOUT", "120"))
    llm_max_retries: int = int(os.getenv("REGWATCH_LLM_RETRIES", "2"))
    llm_temperature: float = float(os.getenv("REGWATCH_LLM_TEMPERATURE", "0.0"))

    # --- Stockage ----------------------------------------------------------
    db_path: str = os.getenv("REGWATCH_DB", str(DATA_DIR / "regwatch.sqlite3"))

    # --- Traçabilité -------------------------------------------------------
    # Toute requête LLM est journalisée (horodatage, modèle, hash du prompt)
    audit_log: bool = os.getenv("REGWATCH_AUDIT", "1") != "0"

    # --- Mode démonstration ------------------------------------------------
    # Instance partagée et publique : plusieurs personnes utilisent le même
    # processus. Le verrou est ici et non dans l'interface, pour qu'aucun
    # écran oublié ne permette d'enregistrer une clé — elle deviendrait
    # active pour tous les autres utilisateurs de l'instance.
    demo_mode: bool = os.getenv("REGWATCH_DEMO", "0") == "1"

    @property
    def llm_available(self) -> bool:
        if self.demo_mode:
            return False
        if self.llm_provider == "offline":
            return False
        if self.llm_provider == "albert":
            return bool(self.albert_api_key)
        return True


settings = Settings()

ENV_FILE = ROOT / ".env"


def chemin_affiche(chemin: str | Path) -> str:
    """Chemin tel qu'il doit apparaître à l'écran : relatif au dossier de
    l'application.

    L'application est déployée sur des postes dont l'arborescence diffère ;
    un chemin absolu affiché dans l'interface ne veut rien dire pour la
    personne d'en face — et donne au passage le nom de session Windows du
    poste sur lequel la copie a été préparée. Le chemin relatif, lui, est le
    même partout.
    """
    p = Path(chemin)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except Exception:
        return p.name


def apply_runtime_settings(persist: bool = True, **changes) -> None:
    """Applique une modification de configuration sans redémarrer l'application.

    `Settings` est figé pour éviter les modifications accidentelles au fil du
    code ; on force ici l'écriture sur l'instance partagée, ce qui est le seul
    moyen de propager le changement aux modules qui l'ont déjà importée.
    Le contournement est volontaire et cantonné à cette fonction.
    """
    env_map = {
        "albert_api_key": "ALBERT_API_KEY",
        "albert_base_url": "ALBERT_BASE_URL",
        "llm_provider": "REGWATCH_LLM_PROVIDER",
        "llm_model": "REGWATCH_LLM_MODEL",
    }
    if settings.demo_mode:
        raise PermissionError(
            "Instance de démonstration : la configuration du modèle est "
            "verrouillée. Installez l'application sur votre poste pour "
            "utiliser votre propre clé.")
    for key, value in changes.items():
        if not hasattr(settings, key):
            raise KeyError(f"paramètre inconnu : {key}")
        object.__setattr__(settings, key, value)
        if key in env_map:
            os.environ[env_map[key]] = str(value)

    if persist:
        write_env_file({env_map[k]: str(v) for k, v in changes.items()
                        if k in env_map})


def write_env_file(values: dict[str, str]) -> Path:
    """Met à jour le fichier .env en préservant les lignes existantes."""
    lines: list[str] = []
    seen: set[str] = set()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            name = line.split("=", 1)[0].strip()
            if name in values:
                lines.append(f"{name}={values[name]}")
                seen.add(name)
            else:
                lines.append(line)
    for name, value in values.items():
        if name not in seen:
            lines.append(f"{name}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        ENV_FILE.chmod(0o600)  # la clé ne doit pas être lisible par d'autres
    except Exception:
        pass
    return ENV_FILE


# ---------------------------------------------------------------------------
# Identité de l'application
# ---------------------------------------------------------------------------
#
# Le nom d'usage change (RegWatch → MARI(a)SOL) mais pas les variables
# d'environnement ni le nom du dossier : une installation existante doit
# continuer de fonctionner sans que personne ait à toucher son fichier .env.
APP_NOM = "mariasol"
APP_SOUS_TITRE = "Cartographier, comparer, décider"
APP_NOM_LONG = ("Mapping d'Alignement Réglementaire par Intelligence Albert "
                "pour le Suivi des Orientations Législatives")
APP_ORGANISME = "Direction générale des entreprises"
