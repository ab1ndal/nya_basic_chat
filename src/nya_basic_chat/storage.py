# Location: src/nya_basic_chat/storage.py
import json
from pathlib import Path
import time
import mimetypes
from nya_basic_chat.config import HISTORY_FILE, UPLOAD_DIR, PREFS_FILE
import streamlit as st
from typing import Any
from nya_basic_chat.db import (
    load_messages as db_load,
    append_message as db_append,
    clear_thread as db_clear,
)


def load_json(path: Path, default=None) -> dict | None:
    """Load JSON from a file, with optional default."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: Path, data: dict) -> None:
    """Save JSON to a file."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _safe_name(name: str) -> str:
    """Safe name for file."""
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".", " ") else "_" for ch in name)


def save_uploads(uploaded_files: list) -> list[dict]:
    """Save Streamlit UploadedFile objects to disk; return metadata list."""
    saved = []
    ts = time.strftime("%Y%m%d-%H%M%S")
    for uf in uploaded_files:
        name = _safe_name(uf.name)
        out = UPLOAD_DIR / f"{ts}_{name}"
        with open(out, "wb") as f:
            f.write(uf.getbuffer())
        mime = uf.type or mimetypes.guess_type(out.name)[0] or "application/octet-stream"
        saved.append(
            {"name": name, "path": str(out.as_posix()), "mime": mime, "size": out.stat().st_size}
        )
    return saved


def load_prefs() -> dict:
    """Load prefs from file."""
    return load_json(PREFS_FILE) or {}


def save_prefs(data: dict) -> None:
    """Save prefs to file."""
    save_json(PREFS_FILE, data)


def build_history_user(user_id: str, thread_id: str = "default") -> None:
    """Build history from database."""
    if "history" not in st.session_state:
        st.session_state.history = db_load(user_id, thread_id)


def append_user_message(
    user_id: str, role: str, content: Any, attachments: Any = None, thread_id: str = "default"
) -> None:
    db_append(user_id, role, content, attachments or [], thread_id)


def clear_history_user(user_id: str, thread_id: str = "default") -> None:
    db_clear(user_id, thread_id)


def build_history():
    """Build history from file."""
    if "history" not in st.session_state:
        saved = load_json(HISTORY_FILE, default={"messages": []})
        # Backward compat: tuples -> dicts
        msgs = []
        for m in saved.get("messages", []):
            if isinstance(m, (list, tuple)) and len(m) == 2:
                role, content = m
                msgs.append({"role": role, "content": content, "attachments": []})
            elif isinstance(m, dict):
                msgs.append(
                    {
                        "role": m.get("role", "assistant"),
                        "content": m.get("content", ""),
                        "attachments": m.get("attachments", []),
                    }
                )
        st.session_state.history = msgs


def save_history(data: dict) -> None:
    """Save history to file."""
    save_json(HISTORY_FILE, data)
