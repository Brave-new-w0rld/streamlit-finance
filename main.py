import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
# import tradermade as tm
import requests
from dotenv import load_dotenv

load_dotenv()


st.set_page_config(page_title="Simple Finance App", page_icon="💰", layout="wide")

with open("assets\\styles.css") as f:
    st.html(f"<style>{f.read()}</style>")

category_file = "categories.json"

if "categories" not in st.session_state:
    st.session_state.categories = {
        "Uncategorized": []
    }

if os.path.exists(category_file):
    with open(category_file, "r") as f:
        st.session_state.categories = json.load(f)

def save_categories():
    with open(category_file, "w") as f:
        json.dump(st.session_state.categories, f)


def categorize_transactions(df):
    df["Category"] = "Uncategorized"

    for category, keywords in st.session_state.categories.items():
        if category == "Uncategorized" or not keywords:
            continue

        lowered_keywords = [keyword.lower().strip() for keyword in keywords]
        for idx, row in df.iterrows():
            details = row["Description"].lower().strip()
            if details in lowered_keywords:
                df.at[idx, "Category"] = category

    return df


def load_transactions(file):
    try:
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
            df[["Type", "Product", "Started Date", "Completed Date", "Description", "Amount", "Fee", "Currency", "State",
                "Balance"]] \
                = df["Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance"].str.split(
                pat=',', expand=True)
            df = df.drop("Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance", axis=1)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        df.columns = [col.strip() for col in df.columns]
        df["Amount"] = df["Amount"].str.replace(",", "").astype(float)
        df["Completed Date"] = pd.to_datetime(df["Completed Date"], format="%Y-%m-%d %H:%M:%S")
        return categorize_transactions(df)
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return None

def add_keyword_to_category(category, keyword):
    keyword = keyword.strip()
    if keyword and keyword not in st.session_state.categories[category]:
        st.session_state.categories[category].append(keyword)
        save_categories()
        return True
    return False

def clear_filters(start, end):
    st.session_state.currencies = []
    st.session_state.date_slicer = (start, end)
    return

@st.cache_data(ttl=3600)
def get_fx_live(ticker, currencies):
    # FX_API_KEY = os.getenv("FX_API_KEY")
    response = requests.get(f"https://open.er-api.com/v6/latest/{ticker}").json()["rates"]
    rates = {k:v for k, v in response.items() if k in currencies}
    return rates
    # tm.set_rest_api_key(FX_API_KEY)
    # return tm.live(currency=','.join(pairs), fields=["mid"])

def main():
    st.title("Simple Finance Dashboard")

    uploaded_file = st.file_uploader("Upload your transactions file", type=["csv", "xlsx"])

    if uploaded_file is not None:
        df = load_transactions(uploaded_file)

        if df is not None:
            debits_df = df[df["Amount"] <= 0].copy()
            credits_df = df[df["Amount"] > 0].copy()
            debits_df["Amount"] = debits_df["Amount"].apply(lambda x: x * -1)

            currencies = debits_df["Currency"].unique().tolist()
            cur = st.pills("Currencies", options=currencies, label_visibility="hidden", selection_mode="multi", key="currencies")

            st.session_state.debits_df = debits_df.copy()
            st.session_state.credits_df = credits_df.copy()

            if cur:
                st.session_state.debits_df = st.session_state.debits_df.query("Currency in @cur")
                st.session_state.credits_df = st.session_state.credits_df.query("Currency in @cur")

            start_date = df["Completed Date"].min().strftime("%Y-%m-%d")
            end_date = df["Completed Date"].max().strftime("%Y-%m-%d")
            period = st.select_slider("Select period:", key="date_slicer", options=pd.date_range(start=start_date, end=end_date
                                                                                        ).map(
                lambda t: t.strftime('%Y-%m-%d')), value=(start_date, end_date), width=600, label_visibility="hidden")
            st.session_state.debits_df = st.session_state.debits_df.query("`Completed Date` >= @period[0] and "
                                                                          "`Completed Date` <= @period[1]")
            st.session_state.credits_df = st.session_state.credits_df.query(
                "`Completed Date` >= @period[0] and `Completed Date` <= @period[1]")

            st.button("Clear filters", key="clear", on_click=clear_filters, args=(start_date, end_date))

            tab1, tab2 = st.tabs(["Expenses (Debits)", "Receipts (Credits)"])
            with tab1:
                with st.form("upd_cat", clear_on_submit=True):
                    new_category = st.text_input("Add/Delete Category")
                    new_category = new_category.lower().strip().capitalize()
                    add, rem, buf = st.columns([1, 1, 7])
                    add_button = add.form_submit_button("Add Category")
                    del_button = rem.form_submit_button("Delete Category")

                    if add_button and new_category:
                        if new_category not in st.session_state.categories:
                            st.session_state.categories[new_category] = []
                            save_categories()
                            st.rerun()

                    if del_button and new_category:
                        if new_category in st.session_state.categories:
                            st.session_state.categories.pop(new_category)
                            save_categories()
                            st.rerun()

                st.subheader("Your Expenses")
                edited_df = st.data_editor(
                    st.session_state.debits_df[["Completed Date", "State", "Description", "Amount", "Category", "Currency"]],
                    column_config={
                        "Completed Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                        "Amount": st.column_config.NumberColumn("Amount", format="%.2f"),
                        "Category": st.column_config.SelectboxColumn(
                            "Category",
                            options=list(st.session_state.categories.keys())
                        )
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="category_editor"
                )

                save_button = st.button("Apply Changes", type="primary", key="apply")
                if save_button:
                    for idx, row in edited_df.iterrows():
                        new_category = row["Category"]
                        if new_category == st.session_state.debits_df.at[idx, "Category"]:
                            continue
                        descr = row["Description"]
                        st.session_state.debits_df.at[idx, "Category"] = new_category
                        add_keyword_to_category(new_category, descr)

                st.subheader("Expenses Summary")

                pres_cur_exp = st.selectbox(
                    "Currency to present expenses",
                    options=currencies,
                    index=None,
                    placeholder="Choose currency...",
                    label_visibility="collapsed",
                    width=200
                )

                category_totals = st.session_state.debits_df.groupby(["Category", "Currency"])["Amount"].sum().reset_index()
                category_totals["Amount in curr."] = 0.00
                category_totals["Selection"] = True
                category_totals = category_totals.sort_values("Amount", ascending=False)

                if pres_cur_exp:
                    # pairs = []
                    # for tick in currencies:
                    #     pairs.append(tick + pres_cur_exp)
                    rates_live = get_fx_live(pres_cur_exp, currencies)
                    for idx, row in category_totals.iterrows():
                        xrate = rates_live[category_totals.at[idx, "Currency"]]
                    #     xrate = fx_live.loc[fx_live["instrument"] == (category_totals.at[idx, "Currency"] + pres_cur_exp)]["mid"].values[0]
                        category_totals.at[idx, "Amount in curr."] = category_totals.at[idx, "Amount"] * xrate

                exp_summary = st.data_editor(
                    category_totals,
                    column_config={
                        "Amount": st.column_config.NumberColumn("Amount", step=.01),
                        "Amount in curr.": st.column_config.NumberColumn("Amount in curr.", step=.01),
                        "Selection": st.column_config.CheckboxColumn(
                            "Selected",
                            help="Choose items for the spending visual",
                            default=True,
                        )
                    },
                    width=800,
                    hide_index=True,
                    disabled=["Category", "Amount", "Amount in curr.", "Currency"]
                )

                st.session_state.exp_summary = exp_summary

                fig = px.pie(
                    st.session_state.exp_summary[st.session_state.exp_summary["Selection"] == True],
                    values="Amount in curr.",
                    names="Category",
                    title="Expenses by Category",
                    hover_data="Category",
                    hole=0.6,
                    color_discrete_sequence=px.colors.qualitative.Vivid
                )
                fig.update_traces(textposition='inside', textinfo='percent')
                fig.update_layout(legend=dict(
                    yanchor="top",
                    y=0.99,
                    xanchor="left",
                    x=0.01
                ))
                if pres_cur_exp:
                    st.plotly_chart(fig, use_container_width=False)
                    st.metric("**Total Paid**", f"{category_totals["Amount in curr."].sum():,.0f} {pres_cur_exp}")

            with tab2:
                st.subheader("Incoming Summary")

                pres_cur_inc = st.selectbox(
                    "Currency to present income",
                    options=currencies,
                    index=None,
                    placeholder="Choose currency...",
                    label_visibility="collapsed",
                    width=200
                )

                income_df = st.session_state.credits_df
                income_df["Amount in curr."] = 0.00

                if pres_cur_inc:
                    # pairs = []
                    # for tick in currencies:
                    #     pairs.append(tick + pres_cur_inc)

                    rates_live = get_fx_live(pres_cur_inc, currencies)
                    for idx, row in income_df.iterrows():
                        xrate = rates_live[income_df.at[idx, "Currency"]]
                        # xrate = fx_live.loc[fx_live["instrument"] == (income_df.at[idx, "Currency"] + pres_cur_inc)]["mid"].values[0]
                        income_df.at[idx, "Amount in curr."] = income_df.at[idx, "Amount"] * xrate


                inc_summary = st.dataframe(income_df[["Type", "Completed Date", "Description", "Amount", "Amount in curr.", "Fee",
                                         "Currency", "State"]],
                             hide_index=True,
                             column_config={
                                "Completed Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                                "Amount": st.column_config.NumberColumn("Amount", format="%.2f"),
                                "Fee": st.column_config.NumberColumn("Fee", format="%.2f")
                            }
                )

                fig = px.pie(
                    income_df,
                    values="Amount in curr.",
                    names="Description",
                    title="Income Breakdown",
                    hover_data="Description",
                    hole=0.6,
                    color_discrete_sequence=px.colors.qualitative.Vivid
                )
                fig.update_traces(textposition='inside', textinfo='percent')
                fig.update_layout(legend=dict(
                    yanchor="top",
                    y=0.99,
                    xanchor="left",
                    x=0.01
                ))
                if pres_cur_inc:
                    st.plotly_chart(fig, use_container_width=False)
                    st.metric("**Total Received**", f"{income_df["Amount in curr."].sum():,.0f} {pres_cur_inc}")

main()
