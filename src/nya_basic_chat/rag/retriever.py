from openai import OpenAI
from pinecone import Pinecone
from nya_basic_chat.config import get_secret


def embed_query(text):
    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))
    response = client.embeddings.create(model="text-embedding-3-large", input=[text])
    return response.data[0].embedding


def retrieve_chunks(user_id, file_ids, prompt, top_k=8):
    pc = Pinecone(api_key=get_secret("PINECONE_API_KEY"))
    index = pc.Index(get_secret("PINECONE_INDEX_NAME"))

    query_emb = embed_query(prompt)
    namespace = str(user_id)

    results = index.query(
        vector=query_emb,
        namespace=namespace,
        filter={"attachment_id": {"$in": file_ids}},
        top_k=top_k,
        include_metadata=True,
    )

    excerpts = []
    for match in results.matches:
        m = match.metadata
        excerpts.append(f"[{m['file_name']} chunk {m['chunk_index']}]\n{m['content']}")

    return "\n\n".join(excerpts)
