# poetry run streamlit run app.py
from pathlib import Path
import os
import json
import time

import streamlit as st

from dotenv import load_dotenv
from llm_client import chat_once, chat_stream
import mimetypes
import fitz
from PIL import Image
import io
import re

_MATH_RE = re.compile(
    r"(\$\$.*?\$\$|\$[^$\n]+\$|\\\[.*?\\\]|\\\(.*?\\\))",
    re.DOTALL,
)

load_dotenv()

st.set_page_config(page_title="NYA LightChat", page_icon=r"assets/NYA_logo.svg")
HISTORY_FILE = ".chat_history.json"
PREFS_FILE = ".chat_prefs.json"

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


# -------- helpers: upload files ------
def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".", " ") else "_" for ch in name)


def save_uploads(uploaded_files):
    """Save Streamlit UploadedFile objects to disk; return metadata list."""
    saved = []
    ts = time.strftime("%Y%m%d-%H%M%S")
    for uf in uploaded_files:
        name = _safe_name(uf.name)
        # ext = Path(name).suffix.lower()
        out = UPLOAD_DIR / f"{ts}_{name}"
        with open(out, "wb") as f:
            f.write(uf.getbuffer())
        mime = uf.type or mimetypes.guess_type(out.name)[0] or "application/octet-stream"
        saved.append(
            {"name": name, "path": str(out.as_posix()), "mime": mime, "size": out.stat().st_size}
        )
    return saved


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


def get_secret(key, default=None):
    try:
        return st.secrets.get(key) or os.getenv(key) or default
    except Exception:
        return os.getenv(key) or default


def _build_call_kwargs(
    prompt, attachments, pdf_mode, system, model, max_completion_tokens, verbosity, reasoning
):
    kwargs = dict(
        prompt=prompt,
        system=system,
        max_completion_tokens=max_completion_tokens,
        model=model,
        attachments=attachments,
        pdf_mode=pdf_mode,
    )
    # Requires llm_client.chat_once and chat_stream to accept these optional kwargs
    if verbosity:
        kwargs["verbosity"] = verbosity
    if reasoning:
        kwargs["reasoning_effort"] = reasoning
    return kwargs


# -------- helpers: render ------------
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


# -------- helpers: persistence --------
def load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# -------- init session state --------
if "history" not in st.session_state:
    saved = load_json(HISTORY_FILE, default={"messages": []})
    # Backward compat: tuples -> dicts
    msgs = []
    for m in saved.get("messages", []):
        if isinstance(m, (list, tuple)) and len(m) == 2:
            role, content = m
            msgs.append({"role": role, "content": content, "attachments": []})
        elif isinstance(m, dict):
            msgs.append(
                {
                    "role": m.get("role", "assistant"),
                    "content": m.get("content", ""),
                    "attachments": m.get("attachments", []),
                }
            )
    st.session_state.history = msgs

# key to reset uploader after send
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# pending attachments to include in next message (paths after saving)
if "pending_attachments" not in st.session_state:
    st.session_state.pending_attachments = []

if "model" not in st.session_state:
    prefs = load_json(PREFS_FILE, default={})
    st.session_state.model = prefs.get("model", get_secret("OPENAI_MODEL", "gpt-5-mini"))

if "system" not in st.session_state:
    st.session_state.system = (
        "You are a helpful, concise assistant. "
        "Always format math using LaTeX: "
        "inline math inside single dollar signs ($...$), "
        "and block math inside double dollar signs ($$...$$) or \\[...\\]. "
        "Never use plain parentheses for math expressions."
    )

# -------- sidebar controls --------
with st.sidebar:
    st.subheader("PDF handling")
    pdf_mode = st.radio(
        "PDF mode",
        ["text", "image"],
        index=0,
        help="Text is token-cheap; Image is better for scans.",
    )

    st.subheader("Attachments")
    attach_to_next = st.toggle(
        "Attach to next message",
        value=True,
        help="If on, uploaded files will be attached to your next message.",
    )

    uploaded_files = st.file_uploader(
        "Upload images or PDFs",
        type=["png", "jpg", "jpeg", "webp", "jfif", "tif", "tiff", "bmp", "pdf"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.uploader_key}",
    )

    if uploaded_files:
        # Save now so they persist even if the app reruns
        saved = save_uploads(uploaded_files)
        st.session_state.pending_attachments.extend(saved)
        # reset the uploader to avoid duplicate re-attachments on rerun
        st.session_state.uploader_key += 1
        st.rerun()

    # Show pending (to be attached to next message)
    if st.session_state.pending_attachments:
        st.caption("Pending attachments (will be added to your next message):")
        for fm in st.session_state.pending_attachments:
            with st.container(border=True):
                preview_file(fm)

    st.subheader("Settings")
    st.session_state.system = st.text_area("System prompt", value=st.session_state.system)
    # Common picks + custom override
    common_models = [
        st.session_state.model,  # ensure current is present
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
    ]
    # make unique while preserving order
    seen = set()
    model_options = []
    for m in common_models:
        if m and m not in seen:
            seen.add(m)
            model_options.append(m)

    selected_model = st.selectbox("Model", model_options, index=0)

    if selected_model != st.session_state.model:
        st.session_state.model = selected_model
        save_json(PREFS_FILE, {"model": selected_model})

    # Slider mappings
    verbosity = st.select_slider("Verbosity", options=["low", "medium", "high"], value="medium")

    reasoning_effort = st.select_slider(
        "Reasoning effort", options=["minimal", "low", "medium", "high"], value="medium"
    )
    max_completion_tokens = st.slider("Max tokens", 64, 8192, 512, 64)
    streaming = st.toggle("Stream output", value=True)

    st.caption(f"Using model: **{st.session_state.model}**")

    # history actions
    if st.button("💾 Export history"):
        ts = time.strftime("%Y%m%d-%H%M%S")
        st.download_button(
            label="Download .json",
            data=json.dumps({"messages": st.session_state.history}, ensure_ascii=False, indent=2),
            file_name=f"chat_history_{ts}.json",
            mime="application/json",
        )

    if st.button("🧹 Clear history"):
        st.session_state.history = []
        save_json(HISTORY_FILE, {"messages": []})
        st.success("History cleared.")

# -------- render past messages --------
st.title("🤖 NYA LightChat")
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        for fm in msg.get("attachments", []):
            with st.container(border=True):
                preview_file(fm)

# -------- input + response --------
prompt = st.chat_input("Ask me something…")
if prompt:
    # pull attachments
    attachments = st.session_state.pending_attachments if attach_to_next else []

    # add user message
    # add user message to history
    user_msg = {"role": "user", "content": prompt, "attachments": attachments}
    st.session_state.history.append(user_msg)

    with st.chat_message("user"):
        st.markdown(prompt)
        for fm in attachments:
            with st.container(border=True):
                preview_file(fm)

    # clear pending after we used them
    st.session_state.pending_attachments = []

    with st.chat_message("assistant"):
        call_kwargs = _build_call_kwargs(
            prompt=prompt,
            attachments=attachments,
            pdf_mode=pdf_mode,
            system=st.session_state.system,
            model=st.session_state.model,
            max_completion_tokens=max_completion_tokens,
            verbosity=verbosity,
            reasoning=reasoning_effort,
        )
        if streaming:
            # Stream live text for responsiveness, then re-render with LaTeX once complete
            ph = st.empty()
            acc = []
            for delta in chat_stream(**call_kwargs):
                acc.append(delta)
                ph.markdown("".join(acc))  # quick live preview (plain markdown)
            answer = "".join(acc)
            ph.empty()
            render_message_with_latex(answer)  # pretty render with LaTeX
        else:
            answer = chat_once(**call_kwargs)
            render_message_with_latex(answer)

    # persist to disk
    st.session_state.history.append({"role": "assistant", "content": answer, "attachments": []})
    save_json(HISTORY_FILE, {"messages": st.session_state.history})
