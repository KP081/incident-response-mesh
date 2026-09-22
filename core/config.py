import os

MODEL_NAME = "gemini-3.5-flash-lite"

try:
    import streamlit as st
    if "DATABASE_URL" in st.secrets:
        os.environ.setdefault("DATABASE_URL", st.secrets["DATABASE_URL"])
except (ImportError, FileNotFoundError):
    pass
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "sqlite+aiosqlite:///incidents.db"
)

def get_session_service_kwargs() -> dict:
    """asyncpg driver needs ssl passed as a connect_arg, not a URL query
    param -- sqlite driver doesn't understand this kwarg at all."""
    if DATABASE_URL.startswith("postgresql"):
        return {"connect_args": {"ssl": True}}
    return {}