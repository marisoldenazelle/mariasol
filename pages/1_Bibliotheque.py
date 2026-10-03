"""Bibliothèque — import et gestion du corpus."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import store
from core.config import CORPUS_DIR
from core.eurlex import CATALOGUE, recuperer
from core.eurlex import nom_de_machine, nom_depuis_le_document
from core.ingest import (DOC_KINDS, VERSION_KINDS, detect_kind,
                         detect_version_date, detect_version_kind, ingest,
                         read_pages, split_legal_text)
from core.ui import comment_ca_marche, entete_module
from core.retrieval import rebuild_index
from core.wk_parser import MS_CODES, merge_contributions, parse_wk_pdf


entete_module(
    "Quels documents l'outil connaît-il ?",
    "Tous les outils travaillent sur les documents chargés ici, et sur rien "
    "d'autre. Le découpage est déterministe : aucun appel au modèle à l'import.")

comment_ca_marche("bibliotheque")

tab_import, tab_eurlex, tab_corpus = st.tabs(
    ["Importer", "Depuis EUR-Lex", "Corpus"])

# --------------------------------------------------------------------- import
with tab_import:
    files = st.file_uploader(
        "Documents", type=["pdf", "docx"], accept_multiple_files=True,
        help="Commentaires consolidés du Conseil, textes de compromis, "
             "non-papers, comptes rendus.",
    )

    c1, c2 = st.columns(2)
    dossier = c1.text_input("Dossier de négociation", placeholder="CSA2, Omnibus, Data Act…")
    version_label = c2.text_input(
        "Repère de version", placeholder="Compromis 1, 24 juillet 2026",
        help="Sert à ordonner les versions dans la comparaison de textes.")

    c3, c4 = st.columns([2, 1])
    forced = c3.selectbox(
        "Type de document",
        options=[None] + list(DOC_KINDS),
        format_func=lambda k: "Détection automatique" if k is None else DOC_KINDS[k],
    )
    renommer = c4.toggle(
        "Renommer les fichiers EUR-Lex", value=True,
        help="Un fichier téléchargé sur EUR-Lex s'appelle « cellar_ebf17714… » "
             "ou « CELEX_32016R0679_FR_TXT ». L'outil lit alors le titre dans "
             "les premières pages du document · « Règlement omnibus numérique "
             "· COM(2025) 837 ». Le nom reste modifiable dans l'onglet Corpus.")

    if files and st.button("Importer", type="primary", width="stretch"):
        # Un document illisible — PDF tronqué par la messagerie, PDF chiffré,
        # .docx corrompu — ne doit pas emporter le lot entier. Sans ce garde,
        # le premier fichier en défaut affichait une trace Python et les
        # suivants n'étaient jamais traités.
        echecs: list[str] = []
        for f in files:
            dest = None
            with st.status(f"{f.name}", expanded=True) as status:
              try:
                dest = CORPUS_DIR / f.name
                dest.write_bytes(f.getbuffer())
                sha = store.file_sha256(dest)
                doc_id = sha[:16]

                detected = forced or detect_kind(dest)
                st.write(f"Type retenu : **{DOC_KINDS.get(detected, detected)}**")

                # Nature et date du document : détectées depuis l'en-tête,
                # modifiables ensuite. Un compromis de présidence et une
                # proposition de la Commission ne se comparent pas de la même
                # façon, encore faut-il savoir lequel on tient.
                try:
                    entete = read_pages(dest)[:3]
                except Exception:
                    entete = []
                v_kind = detect_version_kind(entete) if entete else "autre"
                v_date = detect_version_date(entete) if entete else ""

                # « cellar_ebf17714-c56e-11f0-8da2-01aa75ed71a1.0010.02_DOC_1 »
                # n'apprend à personne de quel texte il s'agit, et c'est ce
                # nom qu'on relit dans toutes les listes de l'application. On
                # va donc chercher le titre dans le document lui-même.
                nom_document = f.name
                if renommer and nom_de_machine(f.name) and entete:
                    propose = nom_depuis_le_document(entete, f.name)
                    if propose and propose != f.name:
                        nom_document = propose
                        st.write(f"Nom retenu : **{nom_document}**  \n"
                                 f"<span style='color:#898781;font-size:0.85rem'>"
                                 f"fichier : {f.name}</span>",
                                 unsafe_allow_html=True)
                st.write(
                    f"Version détectée : **{VERSION_KINDS.get(v_kind, '—')}**"
                    + (f", datée du {v_date}" if v_date else
                       ", date non trouvée, à renseigner dans l'onglet Corpus"))

                result = ingest(dest, kind=detected)
                if not result.segments:
                    status.update(label=f"{f.name} · aucun contenu exploitable",
                                  state="error")
                    continue

                store.register_document(
                    doc_id, nom_document, dossier, sha,
                    n=len(result.segments), kind=result.kind,
                    author_ms=result.author, version_label=version_label,
                    n_segments=len(result.segments),
                    version_kind=v_kind, version_date=v_date,
                    fichier=dest.name,
                )
                store.save_segments(doc_id, result.segments)

                # Les tableaux de commentaires alimentent en plus le module
                # de positions, qui a son propre modèle de données.
                if result.kind == "wk_table":
                    contribs = merge_contributions(parse_wk_pdf(dest, f.name))
                    store.save_contributions(doc_id, contribs)
                    states = len({c.ms_code for c in contribs})
                    st.write(f"{len(contribs)} contributions · {states} États membres")

                for w in result.warnings:
                    st.warning(w)
                status.update(
                    label=f"{f.name} · {len(result.segments)} segments indexés",
                    state="complete",
                )
              except Exception as exc:
                echecs.append(f.name)
                st.error(
                    f"Ce document n'a pas pu être lu : {type(exc).__name__}, "
                    f"{exc}".strip())
                st.caption(
                    "Causes les plus fréquentes : PDF protégé par mot de "
                    "passe, PDF scanné sans couche texte, fichier tronqué à "
                    "l'envoi. Rouvrez-le puis réenregistrez-le en PDF depuis "
                    "votre lecteur, ou convertissez-le en .docx.")
                status.update(label=f"{f.name} · illisible", state="error")
                # Le fichier a pu être recopié dans data/corpus sans jamais
                # entrer en base : on le retire pour ne pas laisser d'orphelin.
                try:
                    connus = store.list_documents()
                    deja_en_base = (not connus.empty
                                    and connus["name"].eq(f.name).any())
                    if dest is not None and dest.exists() and not deja_en_base:
                        dest.unlink()
                except Exception:
                    pass
        if echecs:
            # Pas de `st.rerun()` ici : il effacerait les messages d'erreur
            # avant que la personne ait pu les lire.
            st.warning(
                f"{len(echecs)} document(s) non importé(s) : "
                + ", ".join(echecs)
                + ". Les autres ont bien été traités et apparaissent dans "
                  "l'onglet Corpus.")
        else:
            st.rerun()

    st.divider()
    with st.expander("Ce que fait l'import, selon le type de document"):
        st.markdown(
            """
| Type | Découpage | Attribution |
|---|---|---|
| Commentaires consolidés | par article, puis par État membre | code pays lu dans le tableau |
| Texte réglementaire | par article, préambule conservé à part | aucune |
| Texte libre | par paragraphe, paragraphes courts regroupés | auteur deviné depuis l'en-tête, corrigeable |

Le découpage ne coupe jamais au milieu d'un paragraphe : un extrait cité doit
pouvoir être retrouvé tel quel dans le document source.
"""
        )

# -------------------------------------------------------------------- EUR-Lex
with tab_eurlex:
    st.markdown(
        "Récupérer directement un texte publié au Journal officiel, sans "
        "passer par le téléchargement manuel d'un PDF."
    )
    st.caption(
        "C'est la **version HTML** qui est récupérée, et non le PDF : le PDF "
        "du Journal officiel est une mise en page, deux colonnes, césures, "
        "en-têtes insérés dans le texte, dont l'extraction introduit des "
        "écarts qui se comptent ensuite comme des modifications dans une "
        "comparaison de versions. Le HTML, lui, porte la structure des "
        "articles et donne un texte stable d'une version à l'autre. En "
        "contrepartie, la pagination du JO est perdue : les numéros de page "
        "affichés dans les citations sont des repères internes."
    )

    e1, e2 = st.columns([2, 1])
    choix = e1.selectbox(
        "Texte", options=["— saisir une référence —"] + list(CATALOGUE))
    langue = e2.selectbox("Langue", ["FR", "EN"], index=0,
                          help="La version anglaise sert aux comparaisons avec "
                               "les textes de négociation, rédigés en anglais.")
    reference = (CATALOGUE.get(choix) or "") if choix in CATALOGUE else ""
    if not reference:
        reference = st.text_input(
            "Référence, identifiant CELEX ou adresse EUR-Lex",
            placeholder="32023R2854  ·  règlement (UE) 2023/2854  ·  "
                        "https://eur-lex.europa.eu/…")

    e3, e4 = st.columns(2)
    dossier_el = e3.text_input("Dossier de négociation", key="dossier_eurlex",
                               placeholder="Data Act, Omnibus…")
    version_el = e4.text_input(
        "Repère de version", key="version_eurlex",
        placeholder="JO du 22 décembre 2023",
        help="Sert à ordonner les versions dans la comparaison de textes.")

    if st.button("Récupérer depuis EUR-Lex", type="primary", width="stretch",
                 disabled=not reference.strip()):
        with st.status(f"Récupération de {reference}", expanded=True) as status:
            res = recuperer(reference, langue=langue)
            if not res.ok:
                st.error(res.erreur)
                if res.avertissements:
                    with st.expander("Détail des adresses essayées"):
                        for a in res.avertissements:
                            st.caption(f"· {a}")
                st.caption(f"Première adresse tentée : {res.url or '—'}")
                status.update(label="Récupération impossible", state="error")
            else:
                st.write(f"**{res.titre}**")
                st.caption(f"{res.url} · {len(res.texte):,} caractères"
                           .replace(",", " "))
                segments = split_legal_text(res.pages)
                if not segments:
                    st.error("Aucun article reconnu dans le texte récupéré.")
                    status.update(label="Découpage impossible", state="error")
                else:
                    # Le nom doit dire de quel texte il s'agit : « Data Act —
                    # 32023R2854 [FR] », et non un nom de fichier XML.
                    nom = f"{res.titre[:80]} · {res.celex} [{res.langue}]"
                    # Le texte extrait est conservé sur disque : une citation
                    # doit rester vérifiable même si EUR-Lex change de format.
                    fichier = CORPUS_DIR / f"{res.celex}_{res.langue}.txt"
                    fichier.write_text(res.texte, encoding="utf-8")
                    sha = store.file_sha256(fichier)

                    store.register_document(
                        sha[:16], nom, dossier_el, sha, n=0, kind="legal_text",
                        author_ms="", version_label=version_el or res.celex,
                        n_segments=len(segments),
                        version_kind=detect_version_kind(res.pages),
                        version_date=detect_version_date(res.pages),
                        fichier=fichier.name)
                    store.save_segments(sha[:16], segments)

                    for a in res.avertissements:
                        st.warning(a)
                    st.write(f"{len(segments)} articles indexés.")
                    status.update(label=f"{res.celex} · {len(segments)} articles",
                                  state="complete")
                    st.rerun()

    with st.expander("Si EUR-Lex est injoignable depuis ce poste"):
        st.markdown(
            "Le réseau de l'administration filtre parfois les sorties "
            "directes ; le navigateur, lui, passe par le proxy. Dans ce cas :\n"
            "1. ouvrez l'adresse EUR-Lex dans le navigateur ;\n"
            "2. enregistrez la page ou le PDF ;\n"
            "3. chargez le fichier depuis l'onglet **Importer**, en "
            "choisissant le type « Texte réglementaire ».\n\n"
            "Le résultat est identique, à la pagination près."
        )


# --------------------------------------------------------------------- corpus
with tab_corpus:
    docs = store.list_documents()
    if docs.empty:
        st.info("Corpus vide.")
        st.stop()

    view = docs.copy()
    view["Type"] = view.get("kind", pd.Series(dtype=str)).map(
        lambda k: DOC_KINDS.get(k, k or "—"))
    view["Nature"] = view.get("version_kind", pd.Series(dtype=str)).map(
        lambda k: VERSION_KINDS.get(k or "autre", "—"))
    st.dataframe(
        view[["name", "dossier", "Nature", "version_date", "version_label",
              "Type", "author_ms", "n_segments", "imported_at"]].rename(columns={
                  "name": "Document", "dossier": "Dossier",
                  "version_date": "Date de version",
                  "version_label": "Repère libre", "author_ms": "Auteur",
                  "n_segments": "Segments", "imported_at": "Importé le"}),
        width="stretch", hide_index=True,
    )

    st.divider()
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Corriger un document")
        target = st.selectbox(
            "Document", options=list(docs["id"]),
            format_func=lambda i: docs.set_index("id").loc[i, "name"])
        row = docs.set_index("id").loc[target]

        # Le type conditionne les pages où le document apparaît. Une détection
        # erronée à l'import rendait le document invisible là où on le
        # cherchait ; il doit être corrigeable après coup, sans réimport.
        # Le nom est ce qu'on lit dans toutes les listes de l'application :
        # il doit se corriger sans réimport, que la proposition automatique
        # ait été bonne ou non.
        new_name = st.text_input(
            "Nom du document", value=str(row.get("name") or ""),
            help="Proposé à l'import à partir du titre trouvé dans le "
                 "document quand le fichier portait un nom de machine. "
                 "Modifiable à tout moment.")

        types = list(DOC_KINDS)
        actuel = row.get("kind") or "legal_text"
        new_kind = st.selectbox(
            "Type de document", options=types,
            index=types.index(actuel) if actuel in types else 0,
            format_func=lambda k: DOC_KINDS[k],
            help="Corriger le type suffit à rendre le document visible dans "
                 "les pages concernées. Le découpage déjà fait n'est pas "
                 "refait : si le document a été mal découpé, supprimez-le et "
                 "réimportez-le avec le bon type.")
        new_dossier = st.text_input(
            "Dossier", value=row.get("dossier") or "",
            help="Regroupe les versions successives d'un même texte. C'est ce "
                 "qui alimente le fil du texte, dans la comparaison de versions.")

        vk = list(VERSION_KINDS)
        actuel_vk = row.get("version_kind") or "autre"
        new_vkind = st.selectbox(
            "Nature de la version", options=vk,
            index=vk.index(actuel_vk) if actuel_vk in vk else vk.index("autre"),
            format_func=lambda k: VERSION_KINDS[k],
            help="Détectée à l'import depuis l'en-tête du document. "
                 "Corrigez-la si la détection s'est trompée.")
        new_vdate = st.text_input(
            "Date de la version (AAAA-MM-JJ)",
            value=row.get("version_date") or "",
            placeholder="2026-07-24",
            help="Date de publication ou d'établissement du document. Elle "
                 "ordonne les versions dans le fil du texte.")
        new_version = st.text_input("Repère libre", value=row.get("version_label") or "",
                                    placeholder="Compromis 2, après COREPER")
        new_author = st.selectbox(
            "État membre auteur", options=[""] + MS_CODES,
            index=([""] + MS_CODES).index(row.get("author_ms") or ""),
            help="Utile pour les non-papers : conditionne les filtres par État membre.")
        if st.button("Enregistrer", width="stretch"):
            store.register_document(
                target, (new_name.strip() or row["name"]), new_dossier,
                row["sha256"],
                n=int(row["n_contributions"] or 0), kind=new_kind,
                author_ms=new_author, version_label=new_version,
                n_segments=int(row.get("n_segments") or 0),
                version_kind=new_vkind, version_date=new_vdate.strip())
            if new_author:
                with store.connect() as con:
                    con.execute(
                        "UPDATE segments SET ms_code = ? WHERE document_id = ? "
                        "AND (ms_code IS NULL OR ms_code = '')",
                        (new_author, target))
            st.rerun()

    with c2:
        st.subheader("Maintenance")
        if st.button("Reconstruire l'index de recherche", width="stretch"):
            n = rebuild_index()
            st.success(f"Index reconstruit sur {n} segments.")
        to_delete = st.selectbox(
            "Supprimer un document", options=[None] + list(docs["id"]),
            format_func=lambda i: "—" if i is None
            else docs.set_index("id").loc[i, "name"])
        if to_delete and st.button("Confirmer la suppression", width="stretch"):
            store.delete_document(to_delete)
            st.rerun()
