from nya_basic_chat.rag.processor import ingest_file
from nya_basic_chat.rag.retriever import retrieve_chunks
from supabase import create_client
from nya_basic_chat.config import get_secret


def get_supabase():
    return create_client(get_secret("SUPABASE_URL"), get_secret("SUPABASE_SERVICE_ROLE_KEY"))


def inject(system_prompt, user_prompt, user_id, file_ids):
    sb = get_supabase()

    for fid in file_ids:
        row = (
            sb.table("attachment_processing_status")
            .select("*")
            .eq("attachment_id", fid)
            .single()
            .execute()
            .data
        )

        if row is None or row["status"] in ["pending", "error"]:
            attachment = sb.table("attachments").select("*").eq("id", fid).single().execute().data
            ingest_file(attachment)

    context = retrieve_chunks(user_id, file_ids, user_prompt)

    if context.strip():
        updated_system = system_prompt + "\n\nRelevant Document Excerpts\n" + context
    else:
        updated_system = system_prompt

    return updated_system, user_prompt
