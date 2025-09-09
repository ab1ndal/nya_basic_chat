import os
import streamlit as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORY_FILE = ROOT / ".chat_history.json"
PREFS_FILE = ROOT / ".chat_prefs.json"
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def get_secret(key, default=None):
    try:
        return st.secrets.get(key) or os.getenv(key) or default
    except Exception:
        return os.getenv(key) or default
