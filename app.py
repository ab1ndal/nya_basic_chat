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
    load_prefs,
    save_prefs,
    build_history_user,
    append_user_message,
    clear_history_user,
)
from nya_basic_chat.ui import render_message_with_latex
from nya_basic_chat.chat import _build_call_kwargs, run_once, run_stream
from nya_basic_chat.config import get_secret

# from nya_basic_chat.helpers import _build_user_content
from nya_basic_chat.auth import sign_up_and_in
from nya_basic_chat.reset_pass import handle_password_recovery
from nya_basic_chat.feedback import send_graph_email
from nya_basic_chat.rag.inject import inject
from nya_basic_chat.rag.cleanup import cleanup_expired_temp_files
from nya_basic_chat.rag.processor import get_supabase
import uuid
from nya_basic_chat.rag.processor import ingest_file

load_dotenv()

ADMIN_EMAILS = get_secret("ADMIN_EMAILS").split(",")


@st.dialog("Submit Feedback or Feature Request")
def open_feedback_dialog():
    st.subheader("Feedback Form")

    priority = st.selectbox(
        "Priority", ["Low", "Medium", "High", "Critical"], index=1, key="feedback_priority"
    )

    message = st.text_area("Describe the issue or request", height=150, key="feedback_message")

    uploaded_files = st.file_uploader(
        "Attach screenshots or files",
        type=["png", "jpg", "jpeg", "pdf"],
        accept_multiple_files=True,
        key="feedback_uploads",
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Submit", key="submit_feedback_btn"):
            subject = f"[{priority}] Feedback from {st.session_state['user']['email']}"
            body = (
                f"From: {st.session_state['user']['email']}\n"
                f"Priority: {priority}\n\n"
                f"Message:\n{message}\n"
            )
            # DEBUG
            st.write(body)

            try:
                send_graph_email(subject, body, uploaded_files)
                st.success("Your report has been sent")
            except Exception as e:
                st.error(f"Error sending email: {e}")

            # Close dialog
            st.rerun()

    with col2:
        if st.button("Cancel", key="cancel_feedback_btn"):
            st.rerun()


st.set_page_config(page_title="NYA LightChat", page_icon=r"assets/NYA_logo.svg")

handle_password_recovery()

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

        sb = _sb()
        try:
            sb.auth.sign_out()
        except Exception:
            pass
        for k in [
            "_sb_tokens",
            "sb_client",
            "user",
            "history",
            "uploader_key",
            "pending_attachments",
            "history_loaded",
        ]:
            if k in st.session_state:
                del st.session_state[k]
        try:
            sb.postgrest.auth(None)
        except Exception:
            pass
        st.rerun()

# Feedback modal control
if st.sidebar.button("📣 Report or Request Feature", disabled=True):
    open_feedback_dialog()

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
        "Upload documents",
        type=[
            "png",
            "jpg",
            "jpeg",
            "webp",
            "tif",
            "tiff",
            "bmp",
            "pdf",
            "docx",
            "txt",
            "md",
            "xlsx",
        ],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.uploader_key}",
    )
    upload_mode = st.radio(
        "Upload Mode",
        ["Permanent", "Temp"],
        index=0 if prefs.get("upload_mode", "Permanent") == "Permanent" else 1,
        help="Temp files are deleted after seven days",
    )

    category = "personal_temp" if upload_mode == "Temp" else "personal_perm"
    if st.session_state["user"]["email"] in ADMIN_EMAILS:
        is_global = st.toggle("Make Global Document", value=False)
    else:
        is_global = False

    if is_global:
        category = "global_perm"

    if uploaded_files:
        sb = get_supabase()
        for f in uploaded_files:
            attachment_id = str(uuid.uuid4())
            file_bytes = f.read()
            sb.table("attachment_processing_status").insert(
                {"attachment_id": attachment_id, "status": "pending"}
            ).execute()

            ingest_file(
                {
                    "id": attachment_id,
                    "user_id": USER_ID,
                    "file_name": f.name,
                    "file_bytes": file_bytes,
                    "is_temp": upload_mode == "Temp",
                    "category": category,
                }
            )

            sb.table("attachments").insert(
                {
                    "id": attachment_id,
                    "user_id": USER_ID,
                    "file_name": f.name,
                    "file_type": f.type,
                    "is_temp": upload_mode == "Temp",
                    "category": category,
                }
            ).execute()

            st.session_state.pending_attachments.append(attachment_id)

        st.session_state.uploader_key += 1
        st.rerun()

    if st.session_state.pending_attachments:
        st.caption("Pending attachments (will be added to your next message):")
        for fm in st.session_state.pending_attachments:
            with st.container(border=True):
                st.write(f"Attachment ID: {fm}")

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
        "upload_mode": st.session_state.get("upload_mode", "Permanent"),
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
        sb = get_supabase()
        temp_atts = (
            sb.table("attachments")
            .select("*")
            .eq("user_id", USER_ID)
            .eq("is_temp", True)
            .execute()
            .data
        )
        from nya_basic_chat.rag.processor import get_pinecone

        index = get_pinecone()
        for att in temp_atts:
            # delete Pinecone vectors
            try:
                index.delete(namespace=str(USER_ID), delete_all=True)
            except Exception as e:
                print(e)

            # delete DB rows
            sb.table("attachment_processing_status").delete().eq(
                "attachment_id", att["id"]
            ).execute()
            sb.table("attachments").delete().eq("id", att["id"]).execute()


# -------- render past messages --------
st.title("🤖 NYA LightChat")
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"][0]["text"])
        # TODO UPDATE THIS
        for fm in msg.get("attachments", []):
            with st.container(border=True):
                st.write(f"Attachment ID: {fm}")

# -------- input + response --------
prompt = st.chat_input("Ask me something…")
if prompt:
    cleanup_expired_temp_files(USER_ID)
    # pull attachments
    attachments = st.session_state.pending_attachments if attach_to_next else []

    system_prompt, final_user_prompt = inject(
        system_prompt=st.session_state.system,
        user_prompt=prompt,
        user_id=USER_ID,
        file_ids=attachments,
    )

    print("Result of inject:", system_prompt, final_user_prompt)

    # build user content
    user_content = [{"type": "text", "text": final_user_prompt}]
    # _build_user_content(prompt, attachments=attachments, pdf_mode=pdf_mode)

    # add user message
    # add user message to history
    user_msg = {"role": "user", "content": user_content, "attachments": attachments}
    st.session_state.history.append(user_msg)
    append_user_message(USER_ID, "user", user_content, [], THREAD_ID)

    with st.chat_message("user"):
        st.markdown(prompt)
        for fm in attachments:
            with st.container(border=True):
                st.write(f"Attachment ID: {fm}")

    # clear pending after we used them
    st.session_state.pending_attachments = []

    with st.chat_message("assistant"):
        call_kwargs = _build_call_kwargs(
            content=user_content,
            system=system_prompt,
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
    append_user_message(USER_ID, "assistant", answer_parts, [], thread_id=THREAD_ID)
