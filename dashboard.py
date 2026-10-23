import streamlit as st
import pandas as pd
from analytics import process_store
from agent import StoreAgent

st.set_page_config(page_title="Store Analytics", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "user_filter" not in st.session_state:
    st.session_state.user_filter = None
if "book_filter" not in st.session_state:
    st.session_state.book_filter = None

stores = [f"STORE{i}" for i in range(1, 6)]
selected_store = st.sidebar.selectbox("Select Store", stores)

if "current_store" not in st.session_state:
    st.session_state.current_store = selected_store
elif st.session_state.current_store != selected_store:
    st.session_state.current_store = selected_store
    st.session_state.messages = []
    st.session_state.user_filter = None
    st.session_state.book_filter = None
    st.rerun()

view = st.sidebar.radio("Navigation", ["Dashboard", "Orders", "Customers", "Books", "AI Assistant"])

if st.sidebar.button("Reset Filters"):
    st.session_state.user_filter = None
    st.session_state.book_filter = None
    st.rerun()

@st.cache_data
def get_store_data(store_name):
    return process_store(store_name)

data = get_store_data(selected_store)
orders = data["tables"]["orders"]
users = data["tables"]["users"]
books = data["tables"]["books"]
daily_revenue = data["daily_revenue"]

@st.cache_resource
def get_agent(store_name):
    return StoreAgent(orders, users, books)

agent = get_agent(selected_store)

best_ids = data["best_buyer_ids"]
best_users = users[users["user_id"].isin(best_ids)]

best_name = data.get("best_buyer_name")
if not best_name or best_name == "Unknown":
    best_name = best_users.iloc[0]["name"] if not best_users.empty else "Unknown"

best_spent = data.get("best_buyer_spent")
if not best_spent or best_spent == 0.0:
    best_spent = orders[orders["user_id"].isin(best_ids)]["paid_price"].sum()

def apply_actions(actions):
    for act in actions:
        tbl = act.get("target_table")
        ftype = act.get("filter_type")
        val = act.get("filter_value", "")

        if ftype == "reset":
            st.session_state.user_filter = None
            st.session_state.book_filter = None
        elif tbl == "users" and ftype == "email_prefix":
            st.session_state.user_filter = [p.strip().lower() for p in val.split(",") if p.strip()]
        elif tbl == "books" and ftype == "title_regex":
            st.session_state.book_filter = val

if view == "Dashboard":
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Revenue", f"${orders['paid_price'].sum():,.2f}")
    c2.metric("Unique Customers", data["unique_users"])
    c3.metric("Total Orders", f"{len(orders):,}")
    c4.metric("Avg Order Value", f"${orders['paid_price'].mean():,.2f}")

    st.write("")
    col_main, col_side = st.columns([2.5, 1])

    with col_main:
        st.subheader("Revenue over time")
        rev_chart = daily_revenue.copy()
        rev_chart["order_date"] = pd.to_datetime(rev_chart["order_date"])
        st.line_chart(rev_chart.set_index("order_date")["paid_price"])

    with col_side:
        st.subheader("Top Highlights")
        buyer_ids_str = str(data["best_buyer_ids"])
        st.success(f"**Top Buyer:** {best_name}\n\n**Spent:** ${best_spent:,.2f}\n\n**Linked IDs:** `{buyer_ids_str}`")
        st.info(f"**Top Author:**\n\n{data['most_popular_author']}")
        st.metric("Unique Author Sets", data["unique_author_sets"])

    b1, b2 = st.columns(2)
    with b1:
        st.subheader("Top 5 Revenue Days")
        top_days = data["top5_rev"].sort_values("paid_price", ascending=False)
        top_days["order_date"] = pd.Categorical(
            top_days["order_date"], 
            categories=top_days["order_date"], 
            ordered=True
        )
        st.bar_chart(top_days, x="order_date", y="paid_price", y_label="Revenue ($)", height=220)
        st.dataframe(
            top_days.rename(columns={"order_date": "Date", "paid_price": "Revenue ($)"}),
            hide_index=True,
            width="stretch"
        )
    with b2:
        st.subheader("Top Selling Books")
        top_books = (
            orders.merge(books, on="book_id", how="left")
            .groupby("title")["quantity"]
            .sum()
            .nlargest(5)
            .sort_values(ascending=False)
            .reset_index()
        )
        st.bar_chart(top_books, x="title", y="quantity", horizontal=True, height=280)

elif view == "Orders":
    st.subheader("Orders")
    st.dataframe(orders, width="stretch")

elif view == "Customers":
    st.subheader("Customers")
    display_users = users.copy()
    if st.session_state.user_filter:
        regex = f"^({'|'.join(st.session_state.user_filter)})"
        display_users = display_users[display_users["email"].str.lower().str.contains(regex, na=False)]
        st.info(f"Active Filter: Email prefix in {st.session_state.user_filter}")
    st.dataframe(display_users, width="stretch")

elif view == "Books":
    st.subheader("Books")
    display_books = books.copy()
    if st.session_state.book_filter:
        display_books = display_books[display_books["title"].str.contains(st.session_state.book_filter, case=False, regex=True, na=False)]
        st.info(f"Active Filter: Title regex '{st.session_state.book_filter}'")
    st.dataframe(display_books, width="stretch")

elif view == "AI Assistant":
    st.subheader("AI Assistant")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input("Ask a question about the store or send a command...")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    res = agent.ask(prompt)
                    answer = res["response"]
                    actions = res["actions"]
                    st.markdown(answer)
                    if actions:
                        apply_actions(actions)
                        st.toast(f"Applied {len(actions)} action(s)")
                except Exception as e:
                    answer = f"Error: {e}"
                    st.error(answer)

        st.session_state.messages.append({"role": "assistant", "content": answer})