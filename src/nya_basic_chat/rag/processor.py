from datetime import datetime
from supabase import create_client
from openai import OpenAI
from pinecone import Pinecone
from unstructured.partition.auto import partition
from unstructured.documents.elements import Text
import tiktoken
import json
import re
from nya_basic_chat.config import get_secret


def get_supabase():
    return create_client(get_secret("SUPABASE_URL"), get_secret("SUPABASE_SERVICE_ROLE_KEY"))


def get_pinecone():
    pc = Pinecone(api_key=get_secret("PINECONE_API_KEY"))
    return pc.Index(get_secret("PINECONE_INDEX_NAME"))


def classify_document_type(sample_text: str):
    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))
    prompt = f"""
    Classify this document into one of the following:
    - building_code
    - engineering_report
    - textbook
    - specification
    - drawing
    - general_pdf

    Return JSON with keys:
    - doc_type
    - requires_section_parsing (true if building code)
    
    Sample: {sample_text}
    """

    out = client.chat.completions.create(
        model="gpt-5-nano", messages=[{"role": "user", "content": prompt}]
    )

    try:
        data = json.loads(out.choices[0].message.content)
        return data["doc_type"], data["requires_section_parsing"]
    except Exception:
        return "general_pdf", False


def extract_main_sections(chunk: str):
    """Return all top-level section numbers that appear at line starts."""
    MAIN_SECTION_REGEX = r"(?m)^(?P<section>\d{1,3}(?:\.\d+){1,6})"
    return list({m.group("section") for m in re.finditer(MAIN_SECTION_REGEX, chunk)})


def extract_reference_sections(chunk: str, main_sections: list[str]):
    """Return all code references that are not the main headings."""
    REF_SECTION_REGEX = r"\b(\d{1,3}(?:\.\d+){1,6})\b"
    refs = re.findall(REF_SECTION_REGEX, chunk)
    refs = {r for r in refs if r not in main_sections}
    return list(refs)


def fallback_extract_sections_with_llm(chunk: str):
    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))
    prompt = f"""
    Identify ALL building code section numbers in this text.
    Return JSON with:
    - main_sections: array of sections introduced or heading-level
    - reference_sections: array of other sections referenced
    Text: {chunk}
    """
    out = client.chat.completions.create(
        model="gpt-5-nano", messages=[{"role": "user", "content": prompt}]
    )

    try:
        data = json.loads(out.choices[0].message.content)
        return data["main_sections"], data["reference_sections"]
    except Exception:
        return [], []


def extract_text(file_bytes):
    elements = partition(file=file_bytes)
    out = []
    for el in elements:
        if isinstance(el, Text):
            out.append(
                {
                    "text": el.text.strip(),
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

    try:
        file_bytes = attachment_row["file_bytes"]

        elements = extract_text(file_bytes)

        sample_text = " ".join(el["text"] for el in elements[:5])
        doc_type, requires_parsing = classify_document_type(sample_text)

        page_chunks = []  # will hold dicts {page, chunk}

        for el in elements:
            page = el["page"]
            raw_text = el["text"]
            chs = chunk_text(raw_text)

            for ch in chs:
                page_chunks.append({"page": page, "chunk": ch})

        embeddings = embed_text([pc["chunk"] for pc in page_chunks])
        index = get_pinecone()

        namespace = (
            "global"
            if attachment_row.get("category") == "global_perm"
            else str(attachment_row["user_id"])
        )

        pinecone_vectors = []
        for i, (pc, emb) in enumerate(zip(page_chunks, embeddings)):
            chunk_id = f"{attachment_row['id']}_chunk_{i}"
            chunk_text_val = pc["chunk"]

            main_secs, ref_secs = [], []
            if requires_parsing:
                main_secs = extract_main_sections(chunk_text_val)
                ref_secs = extract_reference_sections(chunk_text_val, main_secs)

                if not main_secs:
                    main_secs, ref_secs = fallback_extract_sections_with_llm(chunk_text_val)

            sb.table("chunks").upsert(
                {
                    "id": chunk_id,
                    "attachment_id": attachment_row["id"],
                    "page_number": pc["page"],
                    "chunk_index": i,
                    "content": chunk_text_val,
                    "main_sections": main_secs,
                    "reference_sections": ref_secs,
                }
            ).execute()

            metadata = {
                "attachment_id": str(attachment_row["id"]),
                "file_name": attachment_row["file_name"],
                "page_number": pc["page"],
                "chunk_index": i,
                "doc_type": doc_type,
                "main_sections": main_secs,
                "reference_sections": ref_secs,
                "category": attachment_row["category"],
            }

            pinecone_vectors.append(
                {
                    "id": chunk_id,
                    "values": emb,
                    "metadata": metadata,
                }
            )

        index.upsert(vectors=pinecone_vectors, namespace=namespace)

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
