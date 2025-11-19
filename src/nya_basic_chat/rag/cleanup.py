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
        bucket = "Temp"
        sb.storage.from_(bucket).remove([r["storage_path"]])

        ns = str(user_id)
        prefix = f"{r['id']}_chunk_"
        index.delete(delete_all=False, namespace=ns, ids=[prefix + str(i) for i in range(200)])

        sb.table("attachments").delete().eq("id", r["id"]).execute()
        sb.table("attachment_processing_status").delete().eq("attachment_id", r["id"]).execute()
