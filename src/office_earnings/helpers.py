import base64
import io
import os
from typing import List, Optional, Sequence, Dict, Any
from PIL import Image
import fitz

# ---------- helpers for multimodal content ----------


def _img_bytes_to_data_url(img_bytes: bytes, mime: str = "image/png") -> str:
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _load_image_as_data_url(path: str, max_side: int = 1536) -> str:
    """Load local image, optionally downscale to fit within max_side, return data URL (PNG)."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    scale = min(1.0, float(max_side) / max(w, h))
    if scale < 1.0:
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return _img_bytes_to_data_url(buf.getvalue(), "image/png")


def _pdf_pages_to_data_urls(path: str, dpi: int = 150, max_side: int = 1536) -> List[str]:
    """Render first N pages of a PDF to PNG data URLs."""
    urls: List[str] = []
    doc = fitz.open(path)
    for i in range(len(doc)):
        page = doc.load_page(i)
        # DPI controls render size
        pix = page.get_pixmap(dpi=dpi)
        # Optionally downscale large pages to max_side
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        w, h = img.size
        scale = min(1.0, float(max_side) / max(w, h))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="PNG")
        urls.append(_img_bytes_to_data_url(out.getvalue(), "image/png"))
    return urls


def _extract_pdf_text(path: str) -> str:
    """Plain-text extraction from PDF"""
    doc = fitz.open(path)
    chunks: List[str] = []
    for page in doc:
        txt = page.get_text("text")
        if not txt:
            continue
        chunks.append(txt)
    return "\n".join(chunks).strip()


def _build_user_content(
    prompt: str,
    attachments: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    pdf_mode: str = "text",  # "image" or "text"
) -> List[Dict[str, Any]]:
    """
    Build a 'content' array for Chat Completions that mixes text + images.
    attachments: [{"name":..., "path":..., "mime":..., "size":...}, ...]
    """
    parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]

    if not attachments:
        return parts

    for a in attachments:
        path = a.get("path", "")
        mime = (a.get("mime") or "").lower()
        if not path:
            continue

        if mime.startswith("image/"):
            try:
                data_url = _load_image_as_data_url(path)
                parts.append({"type": "image_url", "image_url": {"url": data_url}})
            except Exception:
                # fall back: indicate we couldn't load
                parts.append(
                    {"type": "text", "text": f"[Image failed to load: {os.path.basename(path)}]"}
                )
        elif mime == "application/pdf" or path.lower().endswith(".pdf"):
            if pdf_mode == "image":
                try:
                    urls = _pdf_pages_to_data_urls(path)
                    for u in urls:
                        parts.append({"type": "image_url", "image_url": {"url": u}})
                except Exception:
                    parts.append(
                        {"type": "text", "text": f"[PDF preview failed: {os.path.basename(path)}]"}
                    )
            else:  # text mode
                try:
                    txt = _extract_pdf_text(path)
                    if txt:
                        parts.append(
                            {"type": "text", "text": f"[PDF: {os.path.basename(path)}]\n{txt}"}
                        )
                    else:
                        parts.append(
                            {
                                "type": "text",
                                "text": f"[PDF had no extractable text: {os.path.basename(path)}]",
                            }
                        )
                except Exception:
                    parts.append(
                        {
                            "type": "text",
                            "text": f"[PDF text extraction failed: {os.path.basename(path)}]",
                        }
                    )
        else:
            # Unknown type: attempt tiny preview as text if small
            try:
                if os.path.getsize(path) <= 64 * 1024:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        snippet = f.read(4000)
                    parts.append(
                        {"type": "text", "text": f"[File: {os.path.basename(path)}]\n{snippet}"}
                    )
                else:
                    parts.append(
                        {"type": "text", "text": f"[Attached file: {os.path.basename(path)}]"}
                    )
            except Exception:
                parts.append({"type": "text", "text": f"[Attached file: {os.path.basename(path)}]"})
    return parts
