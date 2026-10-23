import re
import yaml
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import networkx as nx
from dateutil import parser
import os

def load_books(store_dir):
    file_path = f"{store_dir}/books.yaml"
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    df = pd.DataFrame(data)
    df.columns = [c.lstrip(":") for c in df.columns]
    df = df.rename(columns={"id": "book_id"})
    return df.drop_duplicates(subset=["book_id"])

def reconcile_users(users):
    cols = ["name", "address", "phone", "email"]
    records = users.to_dict(orient="records")
    g = nx.Graph()
    for r in records:
        g.add_node(r["user_id"])

    n = len(records)
    for i in range(n):
        for j in range(i+1, n):
            u1, u2 = records[i], records[j]
            diff = sum(1 for c in cols if str(u1.get(c, "")).strip().lower() != str(u2.get(c, "")).strip().lower())
            if diff <= 1:
                g.add_edge(u1["user_id"], u2["user_id"])

    clusters = list(nx.connected_components(g))
    u_map = {uid: cid for cid, comp in enumerate(clusters) for uid in comp}
    c_map = {cid: list(comp) for cid, comp in enumerate(clusters)}
    return len(clusters), u_map, c_map

def parse_price(value):
    if pd.isna(value):
        return 0.0
    s = str(value).strip().upper()
    rate = 1.2 if ("€" in s or "EUR" in s) else 1.0
    match = re.search(r"\d+(?:\.\d+)?", s)    
    num = float(match.group(0)) if match else 0.0
    return round(num * rate, 2)

def parse_timestamp(value):
    if pd.isna(value):
        return pd.NaT
    s = str(value).strip()
    s = re.sub(r"(?i)p\.m\.", "PM", s)
    s = re.sub(r"(?i)a\.m\.", "AM", s)
    s = s.replace(";", " ").replace(",", " ")
    try:
        return parser.parse(s, fuzzy=True)
    except:
        return pd.NaT

def process_authors(value):
    if pd.isna(value):
        return ("Unknown",)
    parts = [p.strip() for p in re.split(r",|;| and | & ", str(value)) if p.strip()]
    return tuple(sorted(set(parts))) if parts else ("Unknown",)

def process_store(store_dir):
    orders = pd.read_parquet(f"{store_dir}/orders.parquet").drop_duplicates(subset=["id"])
    users = pd.read_csv(f"{store_dir}/users.csv").rename(columns={"id": "user_id"}).drop_duplicates()    
    books = load_books(store_dir)
    books["year"] = pd.to_numeric(books["year"].replace("", None), errors="coerce").astype("Int64")
    orders["timestamp"] = orders["timestamp"].apply(parse_timestamp)
    orders = orders.dropna(subset=["timestamp", "user_id", "book_id"])
    orders["order_date"] = orders["timestamp"].dt.strftime("%Y-%m-%d")

    orders["quantity"] = pd.to_numeric(orders["quantity"], errors="coerce").fillna(1)
    orders["unit_price_usd"] = orders["unit_price"].apply(parse_price)
    orders["paid_price"] = (orders["quantity"] * orders["unit_price_usd"]).round(2)

    unique_users, user_map, cluster_map = reconcile_users(users)
    orders["cluster_id"] = orders["user_id"].map(user_map)

    daily_revenue = (
        orders.groupby("order_date")["paid_price"]
        .sum()
        .reset_index()
        .sort_values("order_date")
    )
    top5_rev = (
        daily_revenue.sort_values("paid_price", ascending=False)
        .head(5)
    )

    books["author_set"] = books["author"].apply(process_authors)
    unique_author_sets = books["author_set"].nunique()

    merged = orders.merge(books, on="book_id", how="left")
    top_author_tuple = (
        merged.groupby("author_set")["quantity"]
        .sum()
        .sort_values(ascending=False)
        .index[0]
    )
    top_author = ", ".join(top_author_tuple)

    top_cluster = (
        orders.groupby("cluster_id")["paid_price"]
        .sum()
        .sort_values(ascending=False)
        .index[0]
    )
    best_buyer_ids = cluster_map[top_cluster]
    best_buyer_spent = orders[orders["cluster_id"] == top_cluster]["paid_price"].sum()
    best_buyer_info = users[users["user_id"].isin(best_buyer_ids)].iloc[0]
    best_buyer_name = best_buyer_info.get("name", "Unknown")

    return {
        "top5_rev": top5_rev,
        "unique_users": unique_users,
        "unique_author_sets": unique_author_sets,
        "most_popular_author": top_author,
        "best_buyer_ids": best_buyer_ids,
        "daily_revenue": daily_revenue,
        "tables": {"orders": orders, "users": users, "books": books}
    }

if __name__ == "__main__":
    stores = [f"STORE{i}" for i in range(1, 6)]
    for store in stores:
        if os.path.exists(store):
            process_store(store)