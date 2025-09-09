# Location: src/nya_basic_chat/ui.py

import re
from pathlib import Path
import streamlit as st
import mimetypes
from PIL import Image
import io
import fitz


_MATH_RE = re.compile(
    r"(\$\$.*?\$\$|\$[^$\n]+\$|\\\[.*?\\\]|\\\(.*?\\\))",
    re.DOTALL,
)


def render_message_with_latex(text: str):
    """
    Render a message that may contain LaTeX delimited by $...$ or $$...$$.
    Note: st.latex renders as block; inline math will still appear on its own line.
    """
    parts = _MATH_RE.split(text or "")
    for part in parts:
        if not part:
            continue
        if part.startswith("$$") and part.endswith("$$"):
            st.latex(part[2:-2])
        elif part.startswith("$") and part.endswith("$"):
            st.latex(part[1:-1])
        else:
            st.markdown(part)


def preview_file(file_meta: dict):
    """Inline preview for images and PDFs, with a safe download button."""
    path = file_meta.get("path", "")
    name = file_meta.get("name", Path(path).name)
    mime = (file_meta.get("mime") or "").lower()
    size = file_meta.get("size", Path(path).stat().st_size if path and Path(path).exists() else 0)

    if not path or not Path(path).exists():
        st.warning(f"⚠️ Missing file: {name}")
        return

    st.caption(f"📎 {name}  •  {mime or 'unknown'}  •  {size} bytes")

    try:
        if mime.startswith("image/"):
            st.image(path, width="stretch")

        elif mime == "application/pdf" or path.lower().endswith(".pdf"):
            try:
                doc = fitz.open(path)
                if doc.page_count:
                    page = doc.load_page(0)
                    pix = page.get_pixmap(dpi=150)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    st.image(img, caption="PDF preview (page 1)", width="stretch")
            except Exception:
                st.info("PDF preview unavailable; file is still saved.")

            # Offer a safe download (local paths don’t open reliably via link_button)
            with open(path, "rb") as f:
                st.download_button(
                    "Download PDF", f, file_name=Path(path).name, mime="application/pdf"
                )

        else:
            # Unknown type: just offer a download
            mime_guess = mime or (mimetypes.guess_type(path)[0] or "application/octet-stream")
            with open(path, "rb") as f:
                st.download_button("Download file", f, file_name=Path(path).name, mime=mime_guess)

    except Exception as e:
        st.error(f"Preview failed: {e}")
