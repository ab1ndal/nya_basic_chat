from openai import OpenAI
from pinecone import Pinecone
from nya_basic_chat.config import get_secret
from nya_basic_chat.rag.processor import get_supabase


def embed_query(text):
    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))
    response = client.embeddings.create(model="text-embedding-3-small", input=[text])
    return response.data[0].embedding


def retrieve_chunks(user_id, file_ids, prompt, top_k=8):
    pc = Pinecone(api_key=get_secret("PINECONE_API_KEY"))
    index = pc.Index(get_secret("PINECONE_INDEX_NAME"))
    sb = get_supabase()

    query_emb = embed_query(prompt)

    personal_perm = index.query(
        vector=query_emb,
        namespace=str(user_id),
        filter={"category": "personal_perm"},
        top_k=top_k,
        include_metadata=True,
    ).matches

    if file_ids:
        personal_temp = index.query(
            vector=query_emb,
            namespace=str(user_id),
            filter={
                "attachment_id": {"$in": file_ids},
                "category": "personal_temp",
            },
            top_k=top_k,
            include_metadata=True,
        ).matches
    else:
        personal_temp = []

    global_perm = index.query(
        vector=query_emb,
        namespace="global",
        filter={"category": "global_perm"},
        top_k=top_k,
        include_metadata=True,
    ).matches

    results = personal_perm + personal_temp + global_perm

    chunk_ids = [match.id for match in results]
    if len(chunk_ids) == 0:
        return ""

    rows = sb.table("chunks").select("*").in_("id", chunk_ids).execute().data

    # Build excerpt output
    out = []
    rows_by_id = {r["id"]: r for r in rows}

    for m in results:
        r = rows_by_id.get(m.id)
        if not r:
            continue
        out.append(
            f"Source: [{m.metadata.get('file_name')} - Page {r['page_number']}]\nContent:\n{r['content']}"
        )

    return "\n".join(out)
