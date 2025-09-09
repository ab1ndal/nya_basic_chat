import json
from pathlib import Path
import time
import mimetypes
from nya_basic_chat.config import HISTORY_FILE, UPLOAD_DIR, PREFS_FILE
import streamlit as st


def load_json(path: Path, default=None) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: Path, data: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _safe_name(name: str) -> str:
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
    return load_json(PREFS_FILE) or {}


def save_prefs(data: dict) -> None:
    save_json(PREFS_FILE, data)


def build_history():
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
    save_json(HISTORY_FILE, data)
