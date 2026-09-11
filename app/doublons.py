"""Contrôle anti-doublon (optionnel) : écriture LCR à envoyer vs FEC déjà comptabilisé.

Même principe que invoice.zoomali.io (`/api/doublons/check`) : le Chef dépose le FEC
déjà saisi, on compare les lignes de tiers (401) de l'écriture qu'on s'apprête à
envoyer. Clé = compte + date (AAAAMMJJ) + débit + crédit en CENTIMES — jamais le n°
de pièce ni le libellé, trop instables. Rapport NON bloquant (DAAT) : l'humain tranche.

Rien n'est stocké : le FEC est lu en mémoire pour cette seule requête (même garde-fou
RGPD que le reste de l'outil, qui ne stocke aucune opération bancaire).
"""
import io
import re

import pandas as pd


def _centimes(v):
    """Montant → entier centimes, robuste (str '1 234,56' | float | None | '')."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return 0
    s = str(v).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return int(round(float(s) * 100))
    except ValueError:
        return 0


def _pcg8(v):
    """Compte normalisé sur 8 caractères — même règle que ecriture.pcg8."""
    chiffres = "".join(c for c in str(v or "") if c.isdigit())
    return (chiffres + "00000000")[:8]


def _date_yyyymmdd(date_jj_mm_aaaa_ou_texte):
    """Date écriture (jj/mm/aaaa) OU date FEC (AAAAMMJJ ou variante) → AAAAMMJJ."""
    d = pd.to_datetime(date_jj_mm_aaaa_ou_texte, format="%d/%m/%Y", errors="coerce")
    if pd.notna(d):
        return d.strftime("%Y%m%d")
    return re.sub(r"\D", "", str(date_jj_mm_aaaa_ou_texte or ""))[:8]


def parser_fec_txt(raw_bytes):
    """Lit un FEC (.txt, norme DGFiP) en DataFrame. Détecte l'encodage et le séparateur
    (tabulation ou point-virgule) — 100% local, aucune dépendance externe."""
    texte = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texte = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texte is None:
        raise ValueError("encodage du FEC non reconnu")
    sep = "\t" if texte.count("\t") >= texte.count(";") else ";"
    df = pd.read_csv(io.StringIO(texte), sep=sep, dtype=str, engine="python")
    df.columns = [c.strip() for c in df.columns]
    return df


def detecter_doublons(ecriture, fec_df):
    """Compare les lignes 401 (tireurs) de l'écriture JoGADM au FEC déjà comptabilisé.

    ecriture : liste de dicts (sortie de construire_ecriture / POST /gadm : Pcg, Date, D, C).
    fec_df   : DataFrame issu de parser_fec_txt.

    Retourne la liste des lignes de `ecriture` (mêmes dicts) jugées déjà comptabilisées.
    Ne compare QUE les comptes 401 (le crédit banque `512` n'a pas vocation à matcher
    une ligne 512 déjà lettrée un autre jour, ça ferait trop de faux positifs).
    """
    col_compte = next((c for c in fec_df.columns if c.lower() in ("comptenum", "compte_num")), None)
    col_date = next((c for c in fec_df.columns if c.lower() in ("ecrituredate", "date_ecriture")), None)
    col_debit = next((c for c in fec_df.columns if c.lower() == "debit"), None)
    col_credit = next((c for c in fec_df.columns if c.lower() == "credit"), None)
    if not all([col_compte, col_date, col_debit, col_credit]):
        raise ValueError("colonnes FEC introuvables (CompteNum / EcritureDate / Debit / Credit)")

    fec_401 = fec_df[fec_df[col_compte].astype(str).str.strip().str.startswith("401")]
    fec_keys = set()
    for _, r in fec_401.iterrows():
        fec_keys.add((
            _pcg8(r[col_compte]),
            _date_yyyymmdd(r[col_date]),
            _centimes(r[col_debit]),
            _centimes(r[col_credit]),
        ))

    doublons = []
    for ligne in ecriture:
        pcg = str(ligne.get("Pcg", "")).strip()
        if not pcg.startswith("401"):
            continue
        cle = (pcg, _date_yyyymmdd(ligne.get("Date")), _centimes(ligne.get("D")), _centimes(ligne.get("C")))
        if cle in fec_keys:
            doublons.append(ligne)
    return doublons
