"""Fabrique les PDF de documentation à partir des fichiers Markdown.

Pourquoi ce script existe. Les guides sont écrits en Markdown parce que c'est
le format qui se relit, se compare et se corrige le plus facilement — un
diff de Markdown se lit, un diff de .docx non. Mais un Markdown envoyé à
quelqu'un qui ne connaît pas le format s'ouvre dans le bloc-notes, plein de
dièses et d'astérisques, et ne se lit pas. Les deux besoins ne s'opposent
que si l'on choisit : la source reste en Markdown, et ce script en tire le
PDF qu'on envoie.

Ce n'est PAS un composant de l'application : il ne tourne qu'au moment de
préparer une livraison, sur le poste de développement, et sa dépendance
(WeasyPrint) figure dans `requirements-dev.txt` et non dans
`requirements.txt`. Les postes qui font tourner l'outil n'en ont pas besoin.

    python tools/build_docs.py

Les PDF sont écrits dans `docs/fr/pdf/`.
"""

from __future__ import annotations

import base64
import re
import sys
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from core.config import APP_NOM_LONG, VERSION_DATE, __version__  # noqa: E402

SORTIE = RACINE / "docs" / "fr" / "pdf"
SOURCES = RACINE / "docs" / "fr"

# Les documents à produire, dans l'ordre où on les remet. Le sous-titre dit à
# qui le document s'adresse : c'est la première question que se pose quelqu'un
# qui reçoit une liasse de sept PDF.
DOCUMENTS = [
    ("DOSSIER.md", "Lisez-moi d'abord",
     "Ce que contient ce dossier, et qui lit quoi"),
    ("README.md", "Présentation générale",
     "Ce que fait l'outil, comment l'installer, ce qu'il garantit"),
    ("DEMARRAGE.md", "Guide d'installation",
     "Pour la personne qui installe l'outil sur un poste, sans rien savoir"),
    ("POUR_LES_TESTEURS.md", "Test d'usage en trente minutes",
     "Pour la personne à qui l'on demande d'essayer l'outil"),
    ("CADRAGE.md", "Note de cadrage",
     "Ce que l'outil est, pour qui, et ce qu'il n'est pas"),
    ("ARCHITECTURE.md", "Architecture du code",
     "Pour la personne qui doit reprendre, auditer ou héberger l'application"),
    ("DEPLOIEMENT_DEMO.md", "Déploiement d'une instance partagée",
     "Options d'hébergement et précautions"),
    ("TEST.md", "Protocole de recette",
     "La vérification à passer avant de mettre en service"),
    ("../../CHANGELOG.md", "Journal des versions",
     "Ce qui a changé, version par version, et pourquoi"),
]

BLEU_FRANCE = "#000091"
ROUGE_MARIANNE = "#e1000f"
ENCRE = "#161616"
GRIS = "#666666"
TRAIT = "#dddddd"


def _logo_encode() -> str:
    """Le logo en data URI : le PDF doit être un fichier unique et autonome."""
    chemin = RACINE / "assets" / "mariasol_logo.png"
    if not chemin.exists():
        return ""
    donnees = base64.b64encode(chemin.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{donnees}"


def _css(titre: str) -> str:
    """Feuille de style d'impression.

    Les couleurs sont celles de la charte : bleu France pour les titres, rouge
    Marianne pour les accents. Le pied de page porte le numéro de version, ce
    qui évite la question « de quelle version parle ce guide ».
    """
    return f"""
@page {{
  size: A4;
  margin: 22mm 20mm 20mm 20mm;
  @top-right {{
    content: "{titre}";
    font-family: "DejaVu Sans", sans-serif;
    font-size: 7.5pt; color: {GRIS};
  }}
  @bottom-left {{
    content: "mariasol {__version__}";
    font-family: "DejaVu Sans", sans-serif;
    font-size: 7.5pt; color: {GRIS};
  }}
  @bottom-right {{
    content: counter(page) " / " counter(pages);
    font-family: "DejaVu Sans", sans-serif;
    font-size: 7.5pt; color: {GRIS};
  }}
}}
@page :first {{ @top-right {{ content: ""; }} }}

body {{
  font-family: "DejaVu Serif", Georgia, serif;
  font-size: 10pt; line-height: 1.55; color: {ENCRE};
  hyphens: auto;
}}
h1, h2, h3, h4, th, .couverture, code, pre, caption {{
  font-family: "DejaVu Sans", "Segoe UI", sans-serif;
}}
h1 {{
  font-size: 19pt; color: {BLEU_FRANCE}; margin: 0 0 0.4em;
  line-height: 1.2; letter-spacing: -0.01em;
}}
h2 {{
  font-size: 13.5pt; color: {BLEU_FRANCE}; margin: 1.6em 0 0.5em;
  padding-bottom: 0.25em; border-bottom: 1px solid {TRAIT};
  break-after: avoid;
}}
h3 {{ font-size: 11pt; color: #1b1b35; margin: 1.2em 0 0.35em;
     break-after: avoid; }}
h4 {{ font-size: 10pt; color: #1b1b35; margin: 1em 0 0.3em; }}
p {{ margin: 0 0 0.6em; }}
ul, ol {{ margin: 0 0 0.7em; padding-left: 1.2em; }}
li {{ margin-bottom: 0.25em; }}
strong {{ color: #000; }}
a {{ color: {BLEU_FRANCE}; text-decoration: none; }}

code {{
  font-family: "DejaVu Sans Mono", monospace; font-size: 8.6pt;
  background: #f4f4f7; padding: 0.08em 0.3em; border-radius: 3px;
}}
pre {{
  background: #f4f4f7; border-left: 3px solid {BLEU_FRANCE};
  padding: 0.7em 0.9em; font-size: 8.4pt; line-height: 1.45;
  white-space: pre-wrap; word-wrap: break-word; margin: 0 0 0.9em;
  break-inside: avoid;
}}
pre code {{ background: none; padding: 0; }}

table {{
  width: 100%; border-collapse: collapse; margin: 0.5em 0 1em;
  font-size: 8.6pt;
}}
th {{
  background: #f0efec; text-align: left; font-weight: 600;
  padding: 0.4em 0.55em; border: 1px solid {TRAIT};
  color: #1b1b35;
}}
td {{ padding: 0.4em 0.55em; border: 1px solid {TRAIT};
      vertical-align: top; }}
tr {{ break-inside: avoid; }}

blockquote {{
  border-left: 3px solid {ROUGE_MARIANNE}; margin: 0 0 0.9em;
  padding: 0.2em 0 0.2em 0.9em; color: #444;
}}
hr {{ border: none; border-top: 1px solid {TRAIT}; margin: 1.6em 0; }}

/* Couverture */
.couverture {{ break-after: page; padding-top: 4mm; }}
.couverture img {{ height: 17mm; margin-bottom: 12mm; }}
.couverture .surtitre {{
  font-size: 8.5pt; letter-spacing: 0.12em; text-transform: uppercase;
  color: {GRIS}; margin-bottom: 0.8em;
}}
.couverture .titre {{
  font-size: 27pt; line-height: 1.12; color: {BLEU_FRANCE};
  font-weight: 700; margin-bottom: 0.35em;
}}
.couverture .soustitre {{
  font-size: 12pt; color: #444; margin-bottom: 2.4em; line-height: 1.4;
}}
.couverture .barre {{
  width: 46mm; height: 3px; background: {ROUGE_MARIANNE}; margin-bottom: 2.4em;
}}
.couverture .pied {{ font-size: 9pt; color: {GRIS}; line-height: 1.7; }}
.couverture .pied b {{ color: {ENCRE}; }}
"""


def _couverture(titre: str, soustitre: str, logo: str) -> str:
    return f"""
<div class="couverture">
  {f'<img src="{logo}" alt="mariasol">' if logo else ''}
  <div class="surtitre">Direction générale des entreprises</div>
  <div class="titre">{titre}</div>
  <div class="barre"></div>
  <div class="soustitre">{soustitre}</div>
  <div class="pied">
    <b>MARI(a)SOL</b> — {APP_NOM_LONG}<br>
    Version {__version__} du {VERSION_DATE}<br>
    Document établi le {date.today().strftime('%d/%m/%Y')}
  </div>
</div>
"""


def _sans_titre_principal(html: str) -> str:
    """Retire le premier <h1> : il est déjà sur la couverture."""
    return re.sub(r"<h1\b[^>]*>.*?</h1>", "", html, count=1, flags=re.S)


def construire(source: Path, titre: str, soustitre: str,
               destination: Path) -> Path:
    import markdown
    from weasyprint import HTML

    texte = source.read_text(encoding="utf-8")
    corps = markdown.markdown(
        texte, extensions=["tables", "fenced_code", "sane_lists", "toc"])
    corps = _sans_titre_principal(corps)
    logo = _logo_encode()

    page = (f"<html><head><meta charset='utf-8'><title>{titre}</title>"
            f"<style>{_css(titre)}</style></head><body>"
            f"{_couverture(titre, soustitre, logo)}{corps}</body></html>")

    destination.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=page, base_url=str(RACINE)).write_pdf(str(destination))
    return destination


def main() -> int:
    SORTIE.mkdir(exist_ok=True)
    produits = []
    for i, (fichier, titre, soustitre) in enumerate(DOCUMENTS):
        source = SOURCES / fichier
        if not source.exists():
            print(f"  absent, ignoré : {fichier}")
            continue
        nom = f"{i}. {titre}.pdf"
        chemin = construire(source, titre, soustitre, SORTIE / nom)
        produits.append(chemin)
        print(f"  {chemin.relative_to(RACINE)}  "
              f"({chemin.stat().st_size // 1024} Ko)")
    print(f"{len(produits)} document(s) produit(s) dans "
          f"{SORTIE.relative_to(RACINE)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
