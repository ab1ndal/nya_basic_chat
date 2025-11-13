# src/nya_basic_chat/db.py
from typing import List, Dict, Any
from nya_basic_chat.auth import _sb


def sb():
    return _sb()


def load_messages(user_id: str, thread_id: str = "default") -> List[Dict[str, Any]]:
    """Return messages sorted oldest to newest."""
    res = (
        sb()
        .table("messages")
        .select("*")
        .eq("user_id", user_id)
        .eq("thread_id", thread_id)
        .order("created_at", desc=False)
        .execute()
    )
    rows = res.data or []
    # normalize to your in-memory shape
    out = []
    for r in rows:
        out.append(
            {"role": r["role"], "content": r["content"], "attachments": r.get("attachments") or []}
        )
    return out


def append_message(
    user_id: str, role: str, content: Any, attachments: Any = None, thread_id: str = "default"
):
    payload = {
        "user_id": user_id,
        "thread_id": thread_id,
        "role": role,
        "content": content,
        "attachments": attachments or [],
    }
    sb().table("messages").insert(payload).execute()


def clear_thread(user_id: str, thread_id: str = "default"):
    sb().table("messages").delete().eq("user_id", user_id).eq("thread_id", thread_id).execute()
