from datetime import datetime
from supabase import create_client
from openai import OpenAI
from pinecone import Pinecone
from unstructured.partition.auto import partition
from unstructured.documents.elements import Text
import tiktoken


from nya_basic_chat.config import get_secret


def get_supabase():
    return create_client(get_secret("SUPABASE_URL"), get_secret("SUPABASE_SERVICE_ROLE_KEY"))


def get_pinecone():
    pc = Pinecone(api_key=get_secret("PINECONE_API_KEY"))
    return pc.Index(get_secret("PINECONE_INDEX_NAME"))


def download_file(storage_path, is_temp):
    sb = get_supabase()
    bucket = "Temp" if is_temp else "Permanent"
    return sb.storage.from_(bucket).download(storage_path)


def extract_text(file_bytes):
    elements = partition(file=file_bytes)
    out = []
    for el in elements:
        if isinstance(el, Text):
            out.append(
                {
                    "text": el.text,
                    "page": getattr(el.metadata, "page_number", None),
                }
            )
    return out


def chunk_text(text, chunk_size=1500, overlap=250):
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)

    chunks = []
    i = 0
    while i < len(tokens):
        sub = tokens[i : i + chunk_size]
        chunks.append(enc.decode(sub))
        i += chunk_size - overlap
    return chunks


def embed_text(chunks):
    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))
    response = client.embeddings.create(model="text-embedding-3-small", input=chunks)
    return [r.embedding for r in response.data]


def ingest_file(attachment_row):
    sb = get_supabase()

    sb.table("attachment_processing_status").upsert(
        {
            "attachment_id": attachment_row["id"],
            "status": "processing",
            "last_updated": datetime.utcnow().isoformat(),
        }
    ).execute()

    try:
        file_bytes = download_file(attachment_row["storage_path"], attachment_row["is_temp"])

        elements = extract_text(file_bytes)
        page_chunks = []  # will hold dicts {page, chunk}

        for el in elements:
            page = el["page"]
            raw_text = el["text"]

            chs = chunk_text(raw_text)  # your overlapping chunker
            for idx, ch in enumerate(chs):
                page_chunks.append({"page": page, "chunk": ch})

        embeddings = embed_text([pc["chunk"] for pc in page_chunks])
        index = get_pinecone()
        if attachment_row.get("category") == "global_perm":
            namespace = "global"
        else:
            namespace = str(attachment_row["user_id"])

        upserts = []
        for i, (chunk, emb) in enumerate(zip(page_chunks, embeddings)):
            upserts.append(
                {
                    "id": f"{attachment_row['id']}_chunk_{i}",
                    "values": emb,
                    "metadata": {
                        "attachment_id": str(attachment_row["id"]),
                        "file_name": attachment_row["file_name"],
                        "page_number": page_chunks[i]["page"],
                        "chunk_index": i,
                        "content": page_chunks[i]["chunk"],
                    },
                }
            )

        index.upsert(vectors=upserts, namespace=namespace)

        sb.table("attachment_processing_status").upsert(
            {
                "attachment_id": attachment_row["id"],
                "status": "ready",
                "last_updated": datetime.utcnow().isoformat(),
            }
        ).execute()

    except Exception as e:
        sb.table("attachment_processing_status").upsert(
            {
                "attachment_id": attachment_row["id"],
                "status": "error",
                "error_message": str(e),
                "last_updated": datetime.utcnow().isoformat(),
            }
        ).execute()
        raise
