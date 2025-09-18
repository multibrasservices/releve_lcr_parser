### Le `app.py` Final pour le Déploiement
# --- IMPORTS DE L'APPLICATION ---
import streamlit as st
import pandas as pd
import pdfplumber
from io import BytesIO
import plotly.express as px
import streamlit.components.v1 as components  # <-- NOUVEL IMPORT

# --- IMPORTS POUR L'AUTHENTIFICATION ---
import streamlit_authenticator as stauth

# --- Constantes pour les noms de colonnes ---
COL_SAISI = "Saisi"
COL_ECHEANCE = "Date d'Échéance"
COL_TIREUR = "Nom du Tireur"
COL_OPERATION = "N° Opération"
COL_MONTANT = "Montant"

# --- Configuration de la page Streamlit ---
st.set_page_config(
    layout="wide",
    page_title="Synthèse LCR",
    page_icon="📊",
    initial_sidebar_state="expanded" # S'assure que la sidebar est ouverte au départ
)

# --- NOUVELLE FONCTION POUR RÉTRACTER LA SIDEBAR ---
def auto_collapse_sidebar():
    # S'assure que cela ne s'exécute qu'une seule fois par session
    if 'sidebar_collapsed' not in st.session_state:
        # Le code JavaScript pour trouver le bouton de la sidebar et cliquer dessus
        js_code = """
        <script>
            setTimeout(function() {
                // Cible le bouton de la sidebar en utilisant un sélecteur stable
                const collapseButton = window.parent.document.querySelector('[data-testid="stSidebarNavCollapseButton"]');
                
                // Vérifie si le bouton existe et si la sidebar est actuellement ouverte
                if (collapseButton && collapseButton.getAttribute('aria-expanded') === 'true') {
                    collapseButton.click();
                }
            }, 7000); // Délai de 7000 millisecondes (7 secondes)
        </script>
        """
        # Injecte le code JavaScript dans l'application
        components.html(js_code, height=0, width=0)
        
        # Marque que l'opération a été effectuée pour cette session
        st.session_state.sidebar_collapsed = True


# --- (Toutes vos autres fonctions restent inchangées) ---
@st.cache_data
def extract_data_from_pdf(file):
    data = []
    table_settings = {"vertical_strategy": "lines", "horizontal_strategy": "text"}
    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                table = page.extract_table(table_settings)
                if table:
                    for row in table[1:]:
                        if not row or len(row) < 5 or not row[0]:
                            continue
                        try:
                            echeance, nom_du_tireur, num_operation, montant_str = row[2], row[0], row[3], row[4]
                            if echeance and montant_str:
                                montant = float(str(montant_str).replace(' ', '').replace(',', '.').replace('€', ''))
                                data.append([echeance, nom_du_tireur, num_operation, montant])
                        except (ValueError, IndexError, TypeError):
                            continue
    except Exception as e:
        st.warning(f"Impossible de lire un fichier PDF. Est-il corrompu ? Erreur: {e}")
    return data

def display_summary(df):
    st.subheader("Synthèse du reste à payer")
    total_a_payer = df[COL_MONTANT].sum() if not df.empty else 0
    nombre_operations = len(df)
    subtotals = df.groupby(df[COL_ECHEANCE].dt.date)[COL_MONTANT].agg(['sum', 'count'])
    subtotals_to_display = subtotals[subtotals['count'] > 1]
    col1, col2 = st.columns([1.5, 1])
    with col1:
        st.metric(label="**TOTAL GÉNÉRAL À PAYER**", value=f"{total_a_payer:,.2f} €", help=f"Basé sur {nombre_operations} opération(s) non saisie(s).")
    with col2:
        if not subtotals_to_display.empty:
            with st.expander("**Sous-totaux par jour (>1 op.)**", expanded=False):
                styled_subtotals = subtotals_to_display[['sum']].rename(columns={'sum': 'Total Journalier (€)'}).style.format({'Total Journalier (€)': '{:,.2f} €'})
                st.dataframe(styled_subtotals, use_container_width=True)
        else:
            st.info("Aucune journée ne contient plus d'une opération à payer.")

def display_plotly_chart(df):
    st.subheader("Visualisation des échéances")
    if df.empty or COL_MONTANT not in df.columns or df[COL_MONTANT].sum() == 0:
        st.info("Aucune donnée à visualiser ou montants nuls.")
        return
    chart_data = df.groupby([df[COL_ECHEANCE].dt.date, COL_TIREUR])[COL_MONTANT].sum().reset_index()
    chart_data = chart_data.rename(columns={COL_ECHEANCE: "Date d'Échéance", COL_MONTANT: "Montant Total", COL_TIREUR: "Nom du Tireur"})
    chart_type_toggle = st.toggle("Voir en Lignes", value=False, help="Passez de l'histogramme à une courbe.")
    if chart_type_toggle:
        fig = px.line(chart_data, x="Date d'Échéance", y="Montant Total", color="Nom du Tireur", title="Total à payer par jour et par tireur", markers=True, labels={'Montant Total': 'Montant Total (€)'})
        fig.update_traces(textposition='top center')
    else:
        fig = px.bar(chart_data, x="Date d'Échéance", y="Montant Total", color="Nom du Tireur", title="Total à payer par jour et par tireur", labels={'Montant Total': 'Montant Total (€)'})
        fig.update_traces(texttemplate='%{value:,.2f}€', textposition='inside')
        fig.update_layout(barmode='stack')
    fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', xaxis_title="Date d'Échéance", yaxis_title="Montant Total (€)", font=dict(family="Arial, sans-serif", size=12), yaxis_tickformat=",.2f", legend_title_text='Tireur')
    st.plotly_chart(fig, use_container_width=True)

def initialize_session_state(uploaded_files):
    current_files_id = "".join(sorted([f.name for f in uploaded_files]))
    if 'last_files_id' not in st.session_state or st.session_state.last_files_id != current_files_id:
        with st.spinner("Analyse des fichiers PDF en cours..."):
            all_data = []
            for file in uploaded_files:
                file_bytes = BytesIO(file.getvalue())
                all_data.extend(extract_data_from_pdf(file_bytes))
            if not all_data:
                st.error("Aucune donnée valide n'a pu être extraite. Vérifiez le format de vos PDFs.")
                st.session_state.df = pd.DataFrame()
                return
            df = pd.DataFrame(all_data, columns=[COL_ECHEANCE, COL_TIREUR, COL_OPERATION, COL_MONTANT])
            df[COL_ECHEANCE] = pd.to_datetime(df[COL_ECHEANCE], format='%d/%m/%y', dayfirst=True, errors='coerce')
            df.insert(0, COL_SAISI, False)
            df.dropna(subset=[COL_ECHEANCE], inplace=True)
            df = df.sort_values(by=COL_ECHEANCE).reset_index(drop=True)
            st.session_state.df = df
            st.session_state.last_files_id = current_files_id
            st.success(f"✅ {len(df)} opérations ont été extraites avec succès !")
            st.rerun()

def to_excel(df):
    output = BytesIO()
    df_display = df.copy()
    if not df_display.empty and all(col in df.columns for col in [COL_ECHEANCE, COL_MONTANT, COL_TIREUR]):
        pivot_df = pd.pivot_table(df_display, values=COL_MONTANT, index=df_display[COL_ECHEANCE].dt.date, columns=COL_TIREUR, aggfunc='sum', fill_value=0)
        pivot_df.index = pd.to_datetime(pivot_df.index).strftime('%d/%m/%Y')
    else:
        pivot_df = pd.DataFrame()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if COL_ECHEANCE in df_display.columns and pd.api.types.is_datetime64_any_dtype(df_display[COL_ECHEANCE]):
            df_display[COL_ECHEANCE] = df_display[COL_ECHEANCE].dt.strftime('%d/%m/%Y')
        df_display.to_excel(writer, index=False, sheet_name='Synthèse LCR')
        if not pivot_df.empty:
            pivot_df.to_excel(writer, sheet_name='ChartData')
        workbook = writer.book
        main_worksheet = writer.sheets['Synthèse LCR']
        money_format = workbook.add_format({'num_format': '#,##0.00 €'})
        try:
            montant_col_idx = df_display.columns.get_loc(COL_MONTANT)
        except KeyError:
            montant_col_idx = -1
        for i, col in enumerate(df_display.columns):
            max_len = df_display[col].astype(str).map(len).max() if not df_display.empty else 0
            if pd.isna(max_len): max_len = 0
            column_len = max(max_len, len(col)) + 2
            if i == montant_col_idx:
                main_worksheet.set_column(i, i, column_len, money_format)
            else:
                main_worksheet.set_column(i, i, column_len)
        if not pivot_df.empty:
            chart_worksheet = writer.sheets['ChartData']
            chart_worksheet.hide()
            chart = workbook.add_chart({'type': 'column', 'subtype': 'stacked'})
            num_dates, num_tireurs = len(pivot_df), len(pivot_df.columns)
            for i in range(num_tireurs):
                col_letter = chr(ord('B') + i)
                chart.add_series({'name': f'=ChartData!${col_letter}$1', 'categories': f'=ChartData!$A$2:$A${num_dates + 1}', 'values': f'=ChartData!${col_letter}$2:${col_letter}${num_dates + 1}'})
            chart.set_title({'name': 'Total des montants par date et par tireur'})
            chart.set_x_axis({'name': 'Date d\'Échéance'})
            chart.set_y_axis({'name': 'Montant Total (€)', 'num_format': '#,##0.00 €'})
            chart.set_legend({'position': 'right'})
            chart.set_size({'width': 720, 'height': 480})
            main_worksheet.insert_chart('J2', chart)
    return output.getvalue()

def main():
    # --- APPEL DE LA NOUVELLE FONCTION ---
    auto_collapse_sidebar()
    
    st.markdown("""<style>.stApp, .stApp div, .stApp span, .stApp p { font-size: 1.1rem; }</style>""", unsafe_allow_html=True)
    st.title("📊 Synthèse des LCR à Payer")
    st.markdown("Chargez vos relevés LCR au format PDF pour générer une synthèse interactive.")
    uploaded_files = st.file_uploader("Sélectionnez un ou plusieurs fichiers PDF", type="pdf", accept_multiple_files=True)
    if not uploaded_files:
        st.info("En attente du chargement de vos fichiers...")
        return
    initialize_session_state(uploaded_files)
    if 'df' not in st.session_state or st.session_state.df.empty:
        return
    st.markdown("---")
    master_df = st.session_state.df
    edited_df = st.data_editor(master_df, column_config={COL_SAISI: st.column_config.CheckboxColumn(f"{COL_SAISI} ?", default=False), COL_ECHEANCE: st.column_config.DateColumn(COL_ECHEANCE, format="DD/MM/YYYY"), COL_TIREUR: st.column_config.TextColumn(COL_TIREUR), COL_OPERATION: st.column_config.TextColumn(COL_OPERATION), COL_MONTANT: st.column_config.NumberColumn(f"{COL_MONTANT} (€)", format="%.2f €"),}, use_container_width=True, hide_index=True, num_rows="dynamic", key="data_editor")
    st.session_state.df = edited_df
    st.markdown("---")
    hide_completed = st.checkbox("Masquer les opérations déjà saisies dans la synthèse", value=False)
    df_for_summary = st.session_state.df
    if hide_completed:
        df_for_summary = df_for_summary[df_for_summary[COL_SAISI] == False]
    display_summary(df_for_summary)
    st.markdown("<hr style='margin: 1.5rem 0;'>", unsafe_allow_html=True)
    display_plotly_chart(df_for_summary)
    st.markdown("---")
    st.subheader("📥 Exporter les données")
    export_option = st.radio("Quelles données souhaitez-vous exporter ?", ('Toutes les opérations (tableau ci-dessus)', 'Uniquement les opérations non-saisies (synthèse)'), horizontal=True, label_visibility="collapsed")
    df_to_export = edited_df if export_option == 'Toutes les opérations (tableau ci-dessus)' else df_for_summary
    file_name = "synthese_lcr_complet.xlsx" if export_option == 'Toutes les opérations (tableau ci-dessus)' else "synthese_lcr_a_payer.xlsx"
    if not df_to_export.empty:
        excel_data = to_excel(df_to_export)
        st.download_button(label="Télécharger en Excel", data=excel_data, file_name=file_name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    else:
        st.warning("Aucune donnée à exporter pour la sélection en cours.")

# --- LOGIQUE DE DÉMARRAGE PRÊTE POUR LE DÉPLOIEMENT ---
if __name__ == "__main__":

    # Copie des secrets en lecture seule vers un dictionnaire modifiable
    credentials = st.secrets["credentials"].to_dict()

    authenticator = stauth.Authenticate(
        credentials,
        st.secrets['cookie']['name'],
        st.secrets['cookie']['key'],
        st.secrets['cookie']['expiry_days']
    )

    authenticator.login()

    if st.session_state["authentication_status"]:
        with st.sidebar:
            st.title(f"Bienvenue *{st.session_state['name']}*")
            authenticator.logout()
            
            st.markdown("---")
            st.info("Version 19.09.25")
            st.info("© multibrasservices")
            
        main()
    elif st.session_state["authentication_status"] is False:
        st.error('Nom d’utilisateur ou mot de passe incorrect')
    elif st.session_state["authentication_status"] is None:
        st.warning('Veuillez entrer votre nom d’utilisateur et votre mot de passe')
