import os
import json
import pandas as pd
from groq import Groq
from dotenv import load_dotenv
from tools import StoreAPI, TOOLS_SCHEMA
import streamlit as st

load_dotenv()

class StoreAgent:
    def __init__(self, orders: pd.DataFrame, users: pd.DataFrame, books: pd.DataFrame):
        self.api = StoreAPI(orders, users, books)
        api_key = os.environ.get("GROQ_API_KEY")
        model_name = os.environ.get("GROQ_MODEL")

        if not api_key or not model_name:
            try:
                api_key = api_key or st.secrets.get("GROQ_API_KEY")
                model_name = model_name or st.secrets.get("GROQ_MODEL")
            except Exception:
                pass

        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable or Streamlit secret is not set")       
        
        self.client = Groq(api_key=api_key.strip("'\" \t\r\n"))
        self.model_name = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
        self.system_prompt = (
            "You are a bookstore analytics assistant and dashboard controller.\n"
            "Never guess numbers, revenue, counts, or ratings.\n"
            "To answer questions regarding counts, revenue, customer orders, or books, ALWAYS use query_database.\n"
            "Do NOT call update_dashboard_filter unless the user explicitly requests to filter or reset the UI view.\n"
            "When calling tools, do not output any preamble or conversational thoughts before the tool call.\n"
            "Database Schema:\n"
            "orders(id, user_id, book_id, quantity, unit_price_usd, paid_price, order_date, shipping);\n"
            "users(user_id, name, address, phone, email);\n"
            "books(book_id, title, author, price, rating)."
        )

    def ask(self, user_prompt: str) -> dict:
        self.api.pending_actions.clear()
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            for _ in range(5):
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=TOOLS_SCHEMA,
                    tool_choice="auto",
                    temperature=0.0
                )
                msg = response.choices[0].message

                if not msg.tool_calls:
                    return {
                        "response": msg.content or "Completed.",
                        "actions": list(self.api.pending_actions)
                    }

                messages.append(msg)

                for tool_call in msg.tool_calls:
                    args = json.loads(tool_call.function.arguments or "{}")
                    result = self.api.execute(tool_call.function.name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(result)
                    })

            return {
                "response": "Exceeded maximum tool iterations.",
                "actions": list(self.api.pending_actions)
            }

        except Exception as e:
            return {
                "response": f"Groq API Error: {str(e)}",
                "actions": []
            }