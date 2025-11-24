from supabase import create_client
from pinecone import Pinecone
from nya_basic_chat.config import get_secret
from datetime import datetime, timezone


def get_supabase():
    return create_client(get_secret("SUPABASE_URL"), get_secret("SUPABASE_SERVICE_ROLE_KEY"))


def get_pinecone():
    pc = Pinecone(api_key=get_secret("PINECONE_API_KEY"))
    return pc.Index(get_secret("PINECONE_INDEX_NAME"))


def cleanup_expired_temp_files(user_id):
    sb = get_supabase()
    index = get_pinecone()

    rows = (
        sb.table("attachments")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_temp", True)
        .execute()
        .data
    )

    now = datetime.now(timezone.utc)
    expired = []
    for r in rows:
        created = datetime.fromisoformat(r["created_at"])
        if (now - created).days >= 7:
            expired.append(r)

    for r in expired:
        ns = str(user_id)
        sb.table("attachment_processing_status").delete().eq("attachment_id", r["id"]).execute()
        sb.table("chunks").delete().eq("attachment_id", r["id"]).execute()
        sb.table("attachments").delete().eq("id", r["id"]).execute()
        try:
            index.delete(namespace=ns, delete_all=True)
        except Exception as e:
            print(e)
