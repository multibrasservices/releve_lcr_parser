"""Le FEC exporté par la GADM est séparé par « | » : il doit se lire (bug du 12/09/2026)."""
import pytest

from app.doublons import detecter_doublons, parser_fec_txt

EN_TETE = ("JournalCode|JournalLib|EcritureNum|EcritureDate|CompteNum|CompteLib|CompAuxNum|CompAuxLib|"
           "PieceRef|PieceDate|EcritureLib|Debit|Credit|EcritureLet|DateLet|ValidDate|Montantdevise|Idevise|")
LIGNE = "51|BANQUE|000123|20260911|40100100|ELVETIS|||000123|20260911|LCR 09.26|00000000748,28|00000000000,00||||||"


@pytest.mark.parametrize("sep", ["|", "\t", ";"])
def test_fec_lisible_quel_que_soit_le_separateur(sep):
    texte = "\r\n".join(l.replace("|", sep) for l in (EN_TETE, LIGNE)) + "\r\n"
    df = parser_fec_txt(texte.encode("cp1252"))
    assert {"CompteNum", "EcritureDate", "Debit", "Credit"} <= set(df.columns)
    assert len(df) == 1


def test_doublon_detecte_sur_fec_gadm():
    df = parser_fec_txt(("\r\n".join((EN_TETE, LIGNE)) + "\r\n").encode("latin-1"))
    ecriture = [
        {"Pcg": "40100100", "Date": "11/09/2026", "D": "748.28", "C": ""},
        {"Pcg": "40100200", "Date": "14/09/2026", "D": "1360.06", "C": ""},
        {"Pcg": "51220000", "Date": "14/09/2026", "D": "", "C": "2108.34"},
    ]
    doublons = detecter_doublons(ecriture, df)
    assert [d["Pcg"] for d in doublons] == ["40100100"]
