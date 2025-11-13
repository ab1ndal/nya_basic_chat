# poetry run streamlit run app.py
# ruff: noqa: E402
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json
import time

import streamlit as st

from dotenv import load_dotenv
from nya_basic_chat.storage import (
    save_uploads,
    load_prefs,
    save_prefs,
    build_history_user,
    append_user_message,
    clear_history_user,
)
from nya_basic_chat.ui import render_message_with_latex, preview_file
from nya_basic_chat.chat import _build_call_kwargs, run_once, run_stream
from nya_basic_chat.config import get_secret
from nya_basic_chat.helpers import _build_user_content
from nya_basic_chat.auth import sign_up_and_in

load_dotenv()

st.set_page_config(page_title="NYA LightChat", page_icon=r"assets/NYA_logo.svg")

# -------- auth gate --------
user = sign_up_and_in()
if not user:
    st.stop()
st.session_state["user"] = user
st.sidebar.success(f"Signed in as {user['email']}")

USER_ID = user["id"]
THREAD_ID = "default"

with st.sidebar:
    if st.button("Sign out"):
        from nya_basic_chat.auth import _sb

        _sb().auth.sign_out()
        st.session_state.sb_session = None
        st.rerun()
# -------- init session state --------
if "history_loaded" not in st.session_state:
    build_history_user(USER_ID, THREAD_ID)
st.session_state.history_loaded = True

prefs = load_prefs()

# key to reset uploader after send
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# pending attachments to include in next message (paths after saving)
if "pending_attachments" not in st.session_state:
    st.session_state.pending_attachments = []

if "model" not in st.session_state:
    st.session_state.model = prefs.get("model", get_secret("OPENAI_MODEL", "gpt-5-mini"))

if "system" not in st.session_state:
    st.session_state.system = prefs.get(
        "system",
        (
            "You are a helpful, concise assistant. "
            "Always format math using LaTeX: "
            "inline math inside single dollar signs ($...$), "
            "and block math inside double dollar signs ($$...$$) or \\[...\\]. "
            "Never use plain parentheses for math expressions."
        ),
    )

# -------- sidebar controls --------
with st.sidebar:
    st.subheader("PDF handling")
    pdf_mode = st.radio(
        "PDF mode",
        ["text", "image"],
        index=0 if prefs.get("pdf_mode", "text") == "text" else 1,
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
    model_options = list(
        dict.fromkeys(
            [
                st.session_state.model,
                "gpt-5",
                "gpt-5-mini",
                "gpt-5-nano",
            ]
        )
    )
    selected_model = st.selectbox("Model", model_options, index=0, key="model")

    verbosity = st.select_slider(
        "Verbosity",
        options=["low", "medium", "high"],
        value=prefs.get("verbosity", "medium"),
        key="verbosity",
    )
    reasoning_effort = st.select_slider(
        "Reasoning effort",
        options=["minimal", "low", "medium", "high"],
        value=prefs.get("reasoning_effort", "minimal"),
        key="reasoning_effort",
    )
    max_completion_tokens = st.slider(
        "Max tokens",
        64,
        8192,
        prefs.get("max_completion_tokens", 512),
        64,
        key="max_completion_tokens",
    )
    streaming = st.toggle("Stream output", value=prefs.get("streaming", True), key="streaming")

    st.caption(f"Using model: **{st.session_state.model}**")
    prefs_to_save = {
        "model": st.session_state.model,
        "system": st.session_state.system,
        "verbosity": st.session_state.get("verbosity", "medium"),
        "reasoning_effort": st.session_state.get("reasoning_effort", "medium"),
        "max_completion_tokens": st.session_state.get("max_completion_tokens", 512),
        "streaming": st.session_state.get("streaming", True),
        "pdf_mode": st.session_state.get("pdf_mode", "text"),
    }
    save_prefs(prefs_to_save)

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
        clear_history_user(USER_ID, THREAD_ID)
        st.success("History cleared.")

# -------- render past messages --------
st.title("🤖 NYA LightChat")
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"][0]["text"])
        # TODO UPDATE THIS
        for fm in msg.get("attachments", []):
            with st.container(border=True):
                preview_file(fm)

# -------- input + response --------
prompt = st.chat_input("Ask me something…")
if prompt:
    # pull attachments
    attachments = st.session_state.pending_attachments if attach_to_next else []

    # build user content
    user_content = _build_user_content(prompt, attachments=attachments, pdf_mode=pdf_mode)

    # add user message
    # add user message to history
    user_msg = {"role": "user", "content": user_content, "attachments": attachments}
    st.session_state.history.append(user_msg)
    append_user_message(USER_ID, "user", user_content, attachments, THREAD_ID)

    with st.chat_message("user"):
        st.markdown(prompt)
        for fm in attachments:
            with st.container(border=True):
                preview_file(fm)

    # clear pending after we used them
    st.session_state.pending_attachments = []

    with st.chat_message("assistant"):
        call_kwargs = _build_call_kwargs(
            content=user_content,
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
            for delta in run_stream(**call_kwargs):
                acc.append(delta)
                ph.markdown("".join(acc))  # quick live preview (plain markdown)
            answer = "".join(acc)
            ph.empty()
            render_message_with_latex(answer)  # pretty render with LaTeX
        else:
            answer = run_once(**call_kwargs)
            render_message_with_latex(answer)

    # persist to disk
    answer_parts = [{"category": "response", "type": "text", "text": answer}]
    st.session_state.history.append(
        {"role": "assistant", "content": answer_parts, "attachments": []}
    )
    append_user_message(USER_ID, "assistant", answer_parts, attachments=[], thread_id=THREAD_ID)
