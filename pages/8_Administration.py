"""Administration — modèle, données de référence, journal d'audit."""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from core.coalition import POP_FILE, load_populations
from core.config import (ENV_FILE, apply_runtime_settings, chemin_affiche,
                         settings)
from core.llm import get_client, reset_client
from core.retrieval import rebuild_index
from core.store import check_integrity, connect, repair


st.title("Administration")

t1, t2, t3, t4 = st.tabs(
    ["Modèle", "Données de référence", "Index", "Journal d'audit"])

# --------------------------------------------------------------------- modèle
with t1:
    st.subheader("Connexion au fournisseur")

    if settings.demo_mode:
        st.info(
            "**Instance de démonstration.** La configuration du modèle est "
            "verrouillée : cette instance est partagée entre tous ses "
            "utilisateurs, une clé saisie ici deviendrait active pour tout le "
            "monde et son quota serait consommé par d'autres.\n\n"
            "Pour utiliser votre propre clé, installez l'application sur "
            "votre poste : le guide d'installation figure dans le dossier "
            "`documentation/`.",
            icon="🔒")
        st.stop()

    configured = bool(settings.albert_api_key)
    if configured:
        st.success(
            f"Clé enregistrée · fournisseur `{settings.llm_provider}` · "
            f"modèle `{settings.llm_model}`")
    else:
        st.warning(
            "Aucune clé enregistrée. L'import, la recherche plein texte et la "
            "comparaison de versions fonctionnent déjà ; les synthèses "
            "rédigées et la qualification des positions demandent une clé.")

    # --- étape 1 : la clé --------------------------------------------------
    st.markdown("#### 1. Enregistrer la clé")
    c1, c2 = st.columns([2, 1])
    key = c1.text_input(
        "Clé API", type="password",
        placeholder="Collez ici la clé fournie par la DINUM",
        help="Saisie masquée. Elle ne quitte pas cette machine : le serveur "
             "n'écoute que sur localhost.")
    base_url = c2.text_input("Point d'accès", value=settings.albert_base_url)

    persist = st.checkbox(
        "Conserver la clé pour les prochains démarrages", value=True,
        help="Décochez sur un poste partagé : la clé ne vivra alors qu'en "
             "mémoire et disparaîtra à l'arrêt de l'application.")

    if st.button("Enregistrer la clé", type="primary", width="stretch",
                 disabled=not key.strip()):
        apply_runtime_settings(persist=persist,
                               albert_api_key=key.strip(),
                               albert_base_url=base_url.strip(),
                               llm_provider="albert")
        reset_client()
        st.success(
            "Clé enregistrée dans le fichier `.env` du dossier de "
            "l'application (permissions restreintes au propriétaire). "
            "Passez à l'étape 2." if persist else
            "Clé active pour cette session uniquement. Elle sera perdue à "
            "l'arrêt de l'application. Passez à l'étape 2.")
        st.rerun()

    if configured:
        with st.expander("Retirer la clé de ce poste"):
            st.caption(
                "À faire avant de transmettre le dossier de l'application à "
                "quelqu'un d'autre, ou de le copier sur un autre poste : le "
                "fichier `.env` voyage avec le dossier.")
            if st.button("Supprimer la clé enregistrée", width="stretch"):
                apply_runtime_settings(albert_api_key="", llm_provider="offline")
                if ENV_FILE.exists():
                    ENV_FILE.unlink()
                reset_client()
                st.session_state.pop("models", None)
                st.success("Clé supprimée, fichier `.env` effacé.")
                st.rerun()

    # --- étape 2 : le modèle ----------------------------------------------
    st.markdown("#### 2. Choisir le modèle")
    st.caption(
        "L'identifiant du modèle change au fil des mises à jour d'Albert. "
        "Interrogez l'endpoint plutôt que de le deviner.")

    if st.button("Interroger l'endpoint", width="stretch", disabled=not configured):
        try:
            st.session_state["models"] = get_client().list_models()
        except Exception as exc:
            st.error(f"Connexion impossible : {exc}")
            st.caption(
                "Vérifiez la clé, le point d'accès, et que le poste a bien "
                "accès au réseau depuis lequel Albert est joignable.")

    models = st.session_state.get("models", [])
    if models:
        st.caption(f"{len(models)} modèles exposés.")
        default = (models.index(settings.llm_model)
                   if settings.llm_model in models else 0)
        chosen = st.selectbox("Modèle à utiliser", models, index=default)
        if st.button("Enregistrer le modèle", width="stretch"):
            apply_runtime_settings(llm_model=chosen)
            reset_client()
            st.success(f"Modèle `{chosen}` enregistré.")
            st.rerun()
        with st.expander("Voir la liste complète"):
            st.code("\n".join(models))

    # --- étape 3 : vérifier -------------------------------------------------
    st.markdown("#### 3. Vérifier")
    if st.button("Tester la connexion", width="stretch", disabled=not configured):
        ok, msg = get_client().ping()
        (st.success if ok else st.error)(msg)

    st.divider()
    with st.expander("Où va la clé, et ce qui est réellement à risque"):
        st.markdown(
            """
**La saisie dans l'interface n'expose pas plus que l'édition du fichier.**
Le champ est masqué, la valeur transite uniquement vers `localhost`, elle ne
passe par aucun réseau, et aboutit dans le fichier `.env`, à la racine du
dossier de l'application, avec les permissions restreintes au propriétaire.
C'est exactement le même fichier que si vous l'aviez écrit à la main, au
clavier près.

**Ce qui mérite votre attention, en revanche :**

| Point | Ce qui est fait | Ce que vous devez faire |
|---|---|---|
| Écoute réseau | Le serveur est restreint à `localhost` (`.streamlit/config.toml`). Sans cela Streamlit écoute sur toutes les interfaces : n'importe quel poste du réseau ouvrirait l'application, et le corpus, sans authentification. | Ne pas modifier `server.address` sans mettre une authentification devant |
| Copie du dossier |, | Le `.env` voyage avec le dossier. Supprimez la clé avant de transmettre ou de copier l'application sur un autre poste |
| Poste partagé | Le fichier n'est lisible que par votre compte | Décochez « conserver la clé » : elle ne vivra qu'en mémoire |
| Journal d'audit | Seule l'empreinte SHA-256 du prompt est stockée, jamais son contenu ni la clé |, |
| Versionnement | `.env` est dans `.gitignore` | Vérifier avant tout `git add` |

**Le corpus est plus sensible que la clé.** Une clé se révoque ; des documents
LIMITE qui ont fuité, non. C'est pour cette raison que l'écoute réseau est le
premier point de la liste.
"""
        )

    with st.expander("Configuration avancée et modes de fonctionnement"):
        st.markdown(
            """
Les réglages sont enregistrés dans le fichier `.env` du dossier de
l'application et rechargés au démarrage. On peut aussi les y écrire
directement :

```bash
ALBERT_API_KEY=votre_cle
ALBERT_BASE_URL=https://albert.api.etalab.gouv.fr/v1
REGWATCH_LLM_PROVIDER=albert          # albert | openai_compatible | offline
REGWATCH_LLM_MODEL=<identifiant exact du modèle exposé>
```

| Mode | Effet |
|---|---|
| `albert` | API Albert de la DINUM, hébergement SecNumCloud |
| `openai_compatible` | Tout endpoint suivant les conventions OpenAI : LLM interne DGE, modèle exécuté en local |
| `offline` | Aucun appel réseau. Import, indexation, recherche plein texte, comparaison de versions et calculs de coalition restent entièrement fonctionnels |

L'API Albert suit les conventions de l'API OpenAI : le même client sert dans
les trois cas.
"""
        )

# ---------------------------------------------------------- données de référence
with t2:
    st.subheader("Population des États membres")
    st.markdown(
        "Ces chiffres servent au calcul de la majorité qualifiée et des "
        "minorités de blocage. Les valeurs officielles sont fixées chaque "
        "année par une décision du Conseil modifiant son règlement intérieur : "
        "**remplacez-les par celles de l'annexe en vigueur** avant tout usage "
        "en négociation."
    )
    pop = load_populations()
    if pop.empty:
        st.error(f"Fichier introuvable : `{chemin_affiche(POP_FILE)}`")
    else:
        edited = st.data_editor(
            pop.reset_index()[["code", "nom", "population"]],
            width="stretch", hide_index=True, num_rows="fixed",
            column_config={
                "code": st.column_config.TextColumn("Code", disabled=True),
                "nom": st.column_config.TextColumn("État membre", disabled=True),
                "population": st.column_config.NumberColumn("Population", format="%d"),
            },
        )
        c1, c2 = st.columns(2)
        c1.metric("Total", f"{edited['population'].sum() / 1e6:.1f} M")
        c2.metric("Seuil de blocage (35 %)",
                  f"{edited['population'].sum() * 0.35 / 1e6:.1f} M")
        if st.button("Enregistrer les populations", width="stretch"):
            edited.to_csv(POP_FILE, index=False)
            st.success(f"Écrit dans `{chemin_affiche(POP_FILE)}`.")

# ---------------------------------------------------------------------- index
with t3:
    st.subheader("Index de recherche")
    st.markdown(
        "La recherche repose sur un index plein texte SQLite (FTS5), local et "
        "déterministe. Aucun texte ne sort pour être vectorisé, sur des "
        "documents LIMITE, c'est la propriété qui compte le plus. Un résultat "
        "s'explique aussi : on voit quel terme l'a fait remonter."
    )
    with connect() as con:
        try:
            n_seg = con.execute("SELECT count(*) FROM segments").fetchone()[0]
            n_doc = con.execute("SELECT count(*) FROM documents").fetchone()[0]
        except sqlite3.OperationalError:
            n_seg = n_doc = 0
    c1, c2 = st.columns(2)
    c1.metric("Documents", n_doc)
    c2.metric("Segments indexés", n_seg)
    if st.button("Reconstruire l'index", width="stretch"):
        st.success(f"Index reconstruit sur {rebuild_index()} segments.")

    st.caption(f"Base : `{chemin_affiche(settings.db_path)}`, dans le dossier "
               "de l'application.")

    st.divider()
    st.subheader("Santé de la base")
    healthy, message = check_integrity()
    if healthy:
        st.success(message)
    else:
        st.error(f"Anomalie détectée · {message}")
        st.markdown(
            "La réparation reconstruit l'index de recherche **à partir des "
            "documents**. L'index est une donnée dérivée : rien de ce que vous "
            "avez importé ou analysé n'est perdu."
        )
        if st.button("Réparer la base", type="primary", width="stretch"):
            st.code(repair())
            st.rerun()

    with st.expander("Si la réparation échoue"):
        st.markdown(
            f"""
Dernier recours, sans risque pour les documents d'origine : fermez
l'application, supprimez le fichier `{chemin_affiche(settings.db_path)}` du
dossier de l'application, relancez, puis réimportez vos documents depuis la
Bibliothèque.

Vous perdrez les analyses déjà faites, pas les documents, qui restent sur
votre disque dans `data/corpus/`. Sur un gros corpus déjà analysé, tentez
d'abord la réparation.
"""
        )

# ---------------------------------------------------------------------- audit
with t4:
    st.subheader("Journal des appels au modèle")
    st.caption(
        "Horodatage, modèle sollicité, empreinte SHA-256 du prompt, latence et "
        "conformité au schéma. Le contenu des prompts n'est jamais stocké."
    )
    try:
        con = sqlite3.connect(settings.db_path)
        audit = pd.read_sql_query(
            "SELECT * FROM llm_audit ORDER BY ts DESC LIMIT 1000", con)
        con.close()
    except Exception:
        audit = pd.DataFrame()

    if audit.empty:
        st.caption("Aucun appel enregistré.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Appels", len(audit))
        c2.metric("Taux de conformité", f"{100 * audit['ok'].mean():.0f} %")
        c3.metric("Latence médiane", f"{audit['latency_ms'].median() / 1000:.1f} s")
        st.dataframe(audit, width="stretch", hide_index=True)
        st.download_button(
            "Télécharger le journal (.csv)",
            data=audit.to_csv(index=False).encode("utf-8-sig"),
            file_name="journal_audit.csv", mime="text/csv", width="stretch")
