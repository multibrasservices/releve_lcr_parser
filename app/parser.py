"""Extraction déterministe des relevés LCR (pdfplumber).

Logique portée à l'identique depuis l'ancienne app Streamlit (`app.py`) :
extraction du tableau par lignes/colonnes vectorielles, puis normalisation
des dates (%d/%m/%y) et des montants. Aucune IA — déterministe d'abord.
"""
import io
from datetime import datetime

# Stratégie d'extraction calibrée sur le format des relevés LCR.
TABLE_SETTINGS = {"vertical_strategy": "lines", "horizontal_strategy": "text"}

# Mapping colonnes (positions dans la ligne extraite) — identique à l'ancien parseur.
COL_TIREUR = 0
COL_ECHEANCE = 2
COL_OPERATION = 3
COL_MONTANT = 4


def _parse_montant(montant_str: str) -> float:
    """'1 234,56 €' -> 1234.56. Lève ValueError si non parsable."""
    cleaned = str(montant_str).replace(" ", "").replace(",", ".").replace(" ", "").replace("€", "")
    return float(cleaned)


def parse_lcr(pdf_bytes: bytes) -> list[dict]:
    """Extrait les opérations d'un relevé LCR PDF.

    Retourne une liste de dicts triés par échéance :
      {echeance: 'YYYY-MM-DD', echeance_display: 'DD/MM/YYYY',
       tireur: str, operation: str, montant: float}
    Les lignes dont la date est illisible sont écartées (comme l'ancien parseur).
    """
    import pdfplumber  # import local : accélère le démarrage de l'app

    rows: list[dict] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            table = page.extract_table(TABLE_SETTINGS)
            if not table:
                continue
            for row in table[1:]:
                if not row or len(row) < 5 or not row[COL_TIREUR]:
                    continue
                echeance_raw = row[COL_ECHEANCE]
                montant_raw = row[COL_MONTANT]
                if not echeance_raw or not montant_raw:
                    continue
                try:
                    montant = _parse_montant(montant_raw)
                    dt = datetime.strptime(str(echeance_raw).strip(), "%d/%m/%y")
                except (ValueError, IndexError, TypeError):
                    continue
                rows.append(
                    {
                        "echeance": dt.strftime("%Y-%m-%d"),
                        "echeance_display": dt.strftime("%d/%m/%Y"),
                        "tireur": (row[COL_TIREUR] or "").strip(),
                        "operation": (str(row[COL_OPERATION]) or "").strip() if row[COL_OPERATION] else "",
                        "montant": montant,
                    }
                )

    rows.sort(key=lambda r: r["echeance"])
    return rows
