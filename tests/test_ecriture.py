"""Garde-fou « une écriture = une seule date » (cas BAKITO Chabrières, 12/09/2026)."""
import pytest

from app.ecriture import construire_ecriture, controler_dates, controler_equilibre

SOCIETE = {"nom": "BAKITO", "pcg_512": "512200", "code_journal": "51",
           "nature": "DI", "reglement": "CA"}
COMPTES = {"ELVETIS": "401001", "SBD FRANCE SAS": "401002"}

ELVETIS = {"echeance": "2026-09-11", "tireur": "ELVETIS", "operation": "LCR",
           "montant": 748.28, "releve": "80101564517-LCR-20260904.pdf"}
SBD = {"echeance": "2026-09-14", "tireur": "SBD FRANCE SAS", "operation": "LCR",
       "montant": 1360.06, "releve": "80101564517-LCR-20260904.pdf"}


def blocs(ecriture):
    """Découpe l'écriture en blocs : les 401 jusqu'à leur 512."""
    out, bloc = [], []
    for l in ecriture:
        bloc.append(l)
        if l["C"]:
            out.append(bloc)
            bloc = []
    assert not bloc, "dernier bloc sans ligne 512"
    return out


def somme(ecriture, col):
    return round(sum(float(l[col]) for l in ecriture if l[col]), 2)


def test_deux_echeances_meme_releve_donnent_deux_blocs():
    ecriture = construire_ecriture([ELVETIS, SBD], SOCIETE, COMPTES)
    assert len(ecriture) == 4  # 401 + 512 par échéance
    b = blocs(ecriture)
    assert len(b) == 2
    assert [l["Date"] for l in b[0]] == ["11/09/2026", "11/09/2026"]
    assert [l["Date"] for l in b[1]] == ["14/09/2026", "14/09/2026"]
    assert b[0][0]["Pcg"] == "40100100" and b[0][-1]["Pcg"] == "51220000"
    assert b[0][-1]["C"] == "748.28"
    assert b[1][-1]["C"] == "1360.06"
    assert somme(ecriture, "D") == somme(ecriture, "C") == 2108.34


def test_une_echeance_un_seul_bloc():
    autre = dict(ELVETIS, tireur="SBD FRANCE SAS", montant=10.00)
    ecriture = construire_ecriture([ELVETIS, autre], SOCIETE, COMPTES)
    b = blocs(ecriture)
    assert len(b) == 1 and len(ecriture) == 3
    assert {l["Date"] for l in ecriture} == {"11/09/2026"}
    assert b[0][-1]["C"] == "758.28"


def test_date_piece_impose_la_date_a_tout_le_bloc():
    ecriture = construire_ecriture([ELVETIS, SBD], SOCIETE, COMPTES, date_piece="2026-09-30")
    assert {l["Date"] for l in ecriture} == {"30/09/2026"}
    # l'échéance réelle reste visible
    assert [l["Echeance"] for l in ecriture] == ["11/09/2026"] * 2 + ["14/09/2026"] * 2
    assert somme(ecriture, "D") == somme(ecriture, "C")


def test_bloc_a_dates_melangees_refuse():
    ecriture = construire_ecriture([ELVETIS, SBD], SOCIETE, COMPTES)
    # on bricole : on retire la première 512 → un seul bloc à deux dates
    bricole = [l for l in ecriture if not (l["C"] == "748.28")]
    bricole[-1]["C"] = "2108.34"
    controler_equilibre(bricole)  # équilibré, donc seul le garde-fou des dates le voit
    with pytest.raises(ValueError, match="dates mélangées"):
        controler_dates(bricole)
