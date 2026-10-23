import sqlite3
import pandas as pd

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "Execute a SQL SELECT query against the bookstore SQLite database and return rows as JSON. Use this for all analytical, counting, and data retrieval questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query to execute"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_dashboard_filter",
            "description": "Apply or reset a visual filter on the dashboard views. ONLY use this when the user explicitly asks to filter, narrow down, or reset the UI view.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_table": {
                        "type": "string",
                        "enum": ["users", "books"],
                        "description": "Target table to filter. Optional when filter_type is reset."
                    },
                    "filter_type": {
                        "type": "string",
                        "enum": ["email_prefix", "title_regex", "reset"],
                        "description": "Filter type to apply"
                    },
                    "filter_value": {
                        "type": "string",
                        "description": "Filter argument such as comma-separated prefixes ('s,p') or regex pattern. Optional when filter_type is reset."
                    }
                },
                "required": ["filter_type"]
            }
        }
    }
]

class StoreAPI:
    def __init__(self, orders: pd.DataFrame, users: pd.DataFrame, books: pd.DataFrame):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.pending_actions = []
        self._load_tables(orders, users, books)

    def _load_tables(self, orders: pd.DataFrame, users: pd.DataFrame, books: pd.DataFrame):
        orders_clean = orders.copy()
        users_clean = users.copy()
        books_clean = books.copy()

        for df in [orders_clean, users_clean, books_clean]:
            for col in df.columns:
                if df[col].apply(lambda x: isinstance(x, (list, tuple, dict, set))).any():
                    df[col] = df[col].astype(str)

        orders_clean.to_sql("orders", self.conn, if_exists="replace", index=False)
        users_clean.to_sql("users", self.conn, if_exists="replace", index=False)
        books_clean.to_sql("books", self.conn, if_exists="replace", index=False)
        self.conn.commit()

    def query_database(self, query: str) -> str:
        clean_q = query.strip()
        if not clean_q.lower().startswith("select"):
            return "ERROR: Only SELECT queries are permitted."
        try:
            df = pd.read_sql_query(clean_q, self.conn)
            return df.head(50).to_json(orient="records", date_format="iso")
        except Exception as e:
            return f"Database error: {str(e)}"

    def update_dashboard_filter(self, target_table: str = "users", filter_type: str = "reset", filter_value: str = "") -> str:
        action = {
            "target_table": target_table or "users",
            "filter_type": filter_type,
            "filter_value": filter_value or ""
        }
        self.pending_actions.append(action)
        return f"Filter applied successfully: {action}"

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "query_database":
            return self.query_database(args.get("query", ""))
        elif tool_name == "update_dashboard_filter":
            return self.update_dashboard_filter(
                target_table=args.get("target_table", "users"),
                filter_type=args.get("filter_type", "reset"),
                filter_value=args.get("filter_value", "")
            )
        return f"Unknown tool: {tool_name}"