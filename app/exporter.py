"""Génération du fichier Excel de synthèse LCR.

Port fidèle de la fonction `to_excel` de l'ancienne app Streamlit :
feuille "Synthèse LCR" + feuille cachée "ChartData" (pivot date × tireur)
alimentant un histogramme empilé inséré dans la feuille principale.
"""
from io import BytesIO

import pandas as pd

COL_SAISI = "Saisi"
COL_ECHEANCE = "Date d'Échéance"
COL_TIREUR = "Nom du Tireur"
COL_OPERATION = "N° Opération"
COL_MONTANT = "Montant"


def _rows_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    """Transforme la charge utile JSON du front en DataFrame typé."""
    df = pd.DataFrame(
        [
            {
                COL_SAISI: bool(r.get("saisi", False)),
                COL_ECHEANCE: r.get("echeance"),
                COL_TIREUR: r.get("tireur", ""),
                COL_OPERATION: r.get("operation", ""),
                COL_MONTANT: float(r.get("montant", 0) or 0),
            }
            for r in rows
        ]
    )
    if not df.empty:
        df[COL_ECHEANCE] = pd.to_datetime(df[COL_ECHEANCE], errors="coerce")
        df = df.dropna(subset=[COL_ECHEANCE]).sort_values(by=COL_ECHEANCE).reset_index(drop=True)
    return df


def build_xlsx(rows: list[dict]) -> bytes:
    """Construit le classeur Excel (synthèse + graphique empilé) en mémoire."""
    df = _rows_to_dataframe(rows)
    output = BytesIO()
    df_display = df.copy()

    if not df_display.empty and all(col in df.columns for col in [COL_ECHEANCE, COL_MONTANT, COL_TIREUR]):
        pivot_df = pd.pivot_table(
            df_display,
            values=COL_MONTANT,
            index=df_display[COL_ECHEANCE].dt.date,
            columns=COL_TIREUR,
            aggfunc="sum",
            fill_value=0,
        )
        pivot_df.index = pd.to_datetime(pivot_df.index).strftime("%d/%m/%Y")
    else:
        pivot_df = pd.DataFrame()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        if COL_ECHEANCE in df_display.columns and pd.api.types.is_datetime64_any_dtype(df_display[COL_ECHEANCE]):
            df_display[COL_ECHEANCE] = df_display[COL_ECHEANCE].dt.strftime("%d/%m/%Y")
        df_display.to_excel(writer, index=False, sheet_name="Synthèse LCR")
        if not pivot_df.empty:
            pivot_df.to_excel(writer, sheet_name="ChartData")

        workbook = writer.book
        main_worksheet = writer.sheets["Synthèse LCR"]
        money_format = workbook.add_format({"num_format": "#,##0.00 €"})

        try:
            montant_col_idx = df_display.columns.get_loc(COL_MONTANT)
        except KeyError:
            montant_col_idx = -1

        for i, col in enumerate(df_display.columns):
            max_len = df_display[col].astype(str).map(len).max() if not df_display.empty else 0
            if pd.isna(max_len):
                max_len = 0
            column_len = max(max_len, len(col)) + 2
            if i == montant_col_idx:
                main_worksheet.set_column(i, i, column_len, money_format)
            else:
                main_worksheet.set_column(i, i, column_len)

        if not pivot_df.empty:
            chart_worksheet = writer.sheets["ChartData"]
            chart_worksheet.hide()
            chart = workbook.add_chart({"type": "column", "subtype": "stacked"})
            num_dates, num_tireurs = len(pivot_df), len(pivot_df.columns)
            for i in range(num_tireurs):
                col_letter = chr(ord("B") + i)
                chart.add_series(
                    {
                        "name": f"=ChartData!${col_letter}$1",
                        "categories": f"=ChartData!$A$2:$A${num_dates + 1}",
                        "values": f"=ChartData!${col_letter}$2:${col_letter}${num_dates + 1}",
                    }
                )
            chart.set_title({"name": "Total des montants par date et par tireur"})
            chart.set_x_axis({"name": "Date d'Échéance"})
            chart.set_y_axis({"name": "Montant Total (€)", "num_format": "#,##0.00 €"})
            chart.set_legend({"position": "right"})
            chart.set_size({"width": 720, "height": 480})
            main_worksheet.insert_chart("J2", chart)

    return output.getvalue()
