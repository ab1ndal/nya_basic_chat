from nya_basic_chat.rag.retriever import retrieve_chunks
from supabase import create_client
from nya_basic_chat.config import get_secret


def get_supabase():
    return create_client(get_secret("SUPABASE_URL"), get_secret("SUPABASE_SERVICE_ROLE_KEY"))


def inject(system_prompt, user_prompt, user_id, file_ids):
    context = retrieve_chunks(user_id, file_ids, user_prompt)

    if context.strip():
        updated_system = system_prompt + "\n\nRelevant Document Excerpts\n" + context
    else:
        updated_system = system_prompt

    return updated_system, user_prompt
