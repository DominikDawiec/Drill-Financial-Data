import streamlit as st  
import pandas as pd  
import numpy as np  
from openai import OpenAI  
 
# Klucz API do OpenAI  
client = OpenAI(api_key=st.secrets["OpenAI_key"])  
 
# Wczytaj dane z pliku CSV  
@st.cache_resource  
def load_data(file_path):  
    df = pd.read_csv(file_path)  
    df['Miesiac'] = df['Data'].dt.to_period('M').dt.to_timestamp()  
    ordered_columns = ['Miesiac', 'Data', 'Centrum kosztów', 'Konto', 'Opis', 'Koszty']  
    return df.reindex(columns=ordered_columns)  
 
df = load_data("dane_testowe.csv")  
 
# Wczytaj prompt  
@st.cache_resource  
def load_prompt(filename):  
    with open(filename, 'r', encoding='utf-8') as file:  
        return file.read()  
 
prompt_text = load_prompt("prompt.txt")  
 
# Funkcja do przetwarzania danych  
def get_top_transactions_for_period(df, target_period, n=5, m=4, konto_threshold=0, transaction_threshold=0):  
    result = []  
 
    df_period = df[df['Miesiac'] == target_period]  
    previous_period = (pd.to_datetime(target_period) - pd.DateOffset(months=1)).to_period('M').to_timestamp()  
    df_previous_period = df[df['Miesiac'] == previous_period]  
 
    grouped_centrum = df_period.groupby(['Miesiac', 'Centrum kosztów'])['Koszty'].sum().reset_index()  
 
    for _, centrum_row in grouped_centrum.iterrows():  
        period = centrum_row['Miesiac']  
        centrum = centrum_row['Centrum kosztów']  
        total_cost = centrum_row['Koszty']  
 
        df_subset_centrum = df_period[df_period['Centrum kosztów'] == centrum]  
        grouped_konto = df_subset_centrum.groupby('Konto')['Koszty'].sum().reset_index()  
        top_konta = grouped_konto[grouped_konto['Koszty'] > konto_threshold].reindex(grouped_konto.Koszty.abs().sort_values(ascending=False).index).head(n)  
 
        konto_details = []  
 
        for _, konto_row in top_konta.iterrows():  
            konto = konto_row['Konto']  
            konto_cost = konto_row['Koszty']  
 
            df_subset_konto = df_subset_centrum[df_subset_centrum['Konto'] == konto]  
            top_transactions = df_subset_konto[df_subset_konto['Koszty'] > transaction_threshold].reindex(df_subset_konto.Koszty.abs().sort_values(ascending=False).index).head(m)  
 
            transaction_details = []  
 
            for _, transaction_row in top_transactions.iterrows():  
                transaction_cost = transaction_row['Koszty']  
                transaction_desc = transaction_row['Opis']  
 
                # Szukaj wpisu w dzienniku w poprzednim okresie  
                previous_entry = df_previous_period[(df_previous_period['Centrum kosztów'] == centrum) &  
                                                    (df_previous_period['Opis'] == transaction_desc)]  
                if not previous_entry.empty:  
                    previous_cost = previous_entry['Koszty'].values[0]  
                    previous_desc = previous_entry['Opis'].values[0]  
                    transaction_details.append({  
                        "obecny_opis": transaction_desc,  
                        "obecna_kwota": transaction_cost,  
                        "poprzedni_opis": previous_desc,  
                        "poprzednia_kwota": previous_cost  
                    })  
                else:  
                    transaction_details.append({  
                        "obecny_opis": transaction_desc,  
                        "obecna_kwota": transaction_cost,  
                        "poprzedni_opis": "N/A",  
                        "poprzednia_kwota": "N/A"  
                    })  
 
            konto_details.append({  
                "konto": konto,  
                "kwota_na_koncie": konto_cost,  
                "transakcje": transaction_details  
            })  
 
        prompt_input = {  
            "centrum": centrum,  
            "szczegoly": konto_details  
        }  
 
        result.append({  
            'Okres': period,  
            'Centrum kosztów': centrum,  
            'Suma kosztów': total_cost,  
            'prompt_input': prompt_input  
        })  
 
    return pd.DataFrame(result)  
 
# Funkcja do generowania komentarza przy użyciu OpenAI API  
def get_openai_commentary(prompt):  
    response = client.chat.completions.create(  
        model="gpt-4o",  
        messages=[  
            {"role": "system", "content": "Jesteś doświadczonym analitykiem finansowym odpowiedzialnym za szczegółowe podsumowywanie transakcji na kontach księgowych."},  
            {"role": "user", "content": prompt}  
        ],  
        max_tokens=3000,  
        temperature=0.4  
    )  
    return response.choices[0].message.content  
 
# Inicjalizacja stanu sesji  
if 'result_df' not in st.session_state:  
    st.session_state['result_df'] = None  
if 'commentaries' not in st.session_state:  
    st.session_state['commentaries'] = None  
 
# Interfejs Streamlit  
st.title("GENEROWANIE KOMENTARZY")  
st.subheader("Przykładowe dane")  
 
# Edytowalny DataFrame  
editable_df = st.data_editor(df, use_container_width=True)  
 
# Sortowanie dat  
sorted_dates = sorted(editable_df['Miesiac'].unique())  

st.write("---")

# Wybór okresu  
target_period = st.selectbox("Wybierz okres", sorted_dates)  
 
# Wybór wartości n i m  
n = st.slider("Wybierz liczbę top kont (n)", min_value=1, max_value=10, value=5)  
m = st.slider("Wybierz liczbę top transakcji (m)", min_value=1, max_value=10, value=4)  
 
# Wybór progów kwotowych  
konto_threshold = st.number_input("Wybierz próg kwotowy dla kont", min_value=0, value=0)  
transaction_threshold = st.number_input("Wybierz próg kwotowy dla transakcji", min_value=0, value=0)  
 
# Przycisk do generowania dodatkowych komentarzy  
if st.button("Generuj komentarze", use_container_width=True):  
    st.session_state['result_df'] = get_top_transactions_for_period(editable_df, target_period, n=n, m=m, konto_threshold=konto_threshold, transaction_threshold=transaction_threshold)  
 
    st.session_state['commentaries'] = []  
    for _, row in st.session_state['result_df'].iterrows():  
        prompt = f"{prompt_text}:\n\n{row['prompt_input']}"  
        commentary = get_openai_commentary(prompt)  
        st.session_state['commentaries'].append(commentary)  
 
# Wyświetlenie wyników  
if st.session_state['result_df'] is not None:  
    st.subheader("Suma kosztów w centrach kosztów")  
    grouped_centrum = st.session_state['result_df'].groupby('Centrum kosztów')['Suma kosztów'].sum().reset_index()  
    st.dataframe(grouped_centrum, use_container_width=True)  
 
    if st.session_state['commentaries'] is not None:  
        for commentary in st.session_state['commentaries']:  
            st.markdown(commentary)  
            st.write("---")  
