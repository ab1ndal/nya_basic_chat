from openai import OpenAI
from pinecone import Pinecone
from nya_basic_chat.config import get_secret


def embed_query(text):
    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))
    response = client.embeddings.create(model="text-embedding-3-small", input=[text])
    return response.data[0].embedding


def retrieve_chunks(user_id, file_ids, prompt, top_k=8):
    pc = Pinecone(api_key=get_secret("PINECONE_API_KEY"))
    index = pc.Index(get_secret("PINECONE_INDEX_NAME"))

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

    excerpts = []
    for match in results:
        m = match.metadata
        page = m.get("page_number", "?")
        chunk = m.get("chunk_index", "?")
        file_name = m.get("file_name", "?")
        excerpts.append(f"[{file_name} - page {page}, chunk {chunk}]\n{m['content']}")

    return "\n\n".join(excerpts)
