# src/nya_basic_chat/db.py
from typing import List, Dict, Any
from nya_basic_chat.auth import _sb


def _authed_client():
    client = _sb()
    try:
        sess = client.auth.get_session()
        token = getattr(sess, "access_token", None) or getattr(getattr(sess, "session", None), "access_token", None)
        if token:
            client.postgrest.auth(token)
    except Exception:
        pass
    return client


def load_messages(user_id: str, thread_id: str = "default") -> List[Dict[str, Any]]:
    """Return messages sorted oldest to newest."""
    sb = _authed_client()
    res = (
        sb.table("messages")
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
    sb = _authed_client()
    payload = {
        "user_id": user_id,
        "thread_id": thread_id,
        "role": role,
        "content": content,
        "attachments": attachments or [],
    }
    sb.table("messages").insert(payload).execute()


def clear_thread(user_id: str, thread_id: str = "default"):
    sb = _authed_client()
    sb.table("messages").delete().eq("user_id", user_id).eq("thread_id", thread_id).execute()
