import os
import json
import time
from pathlib import Path

import streamlit as st

from dotenv import load_dotenv
from src.office_earnings.llm_client import chat_once, chat_stream

load_dotenv()

st.set_page_config(page_title="Earnings", page_icon="💲")
HISTORY_FILE = ".chat_history.json"
PREFS_FILE = ".chat_prefs.json"

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


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
    st.session_state.history = saved.get("messages", [])

if "model" not in st.session_state:
    prefs = load_json(PREFS_FILE, default={})
    st.session_state.model = prefs.get("model", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

if "system" not in st.session_state:
    st.session_state.system = "You are a helpful, concise assistant."

# -------- sidebar controls --------
with st.sidebar:
    st.subheader("Settings")

    # Common picks + custom override
    common_models = [
        st.session_state.model,  # ensure current is present
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1-mini",
        "gpt-4.1",
    ]
    # make unique while preserving order
    seen = set()
    model_options = []
    for m in common_models:
        if m and m not in seen:
            seen.add(m)
            model_options.append(m)

    selected_model = st.selectbox("Model", model_options, index=0)
    custom_model = st.text_input(
        "Or custom model id", value="", placeholder="e.g. my-gateway/model"
    )
    effective_model = custom_model.strip() or selected_model
    if effective_model != st.session_state.model:
        st.session_state.model = effective_model
        save_json(PREFS_FILE, {"model": effective_model})

    st.session_state.system = st.text_area("System prompt", value=st.session_state.system)
    temperature = st.slider("Temperature", 0.0, 1.5, 0.2, 0.1)
    max_tokens = st.slider("Max tokens", 64, 4096, 512, 64)
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
st.title("🤖 OpenAI Chat (Poetry • 3.13.3)")
for role, content in st.session_state.history:
    with st.chat_message(role):
        st.markdown(content)

# -------- input + response --------
prompt = st.chat_input("Ask me something…")
if prompt:
    # pull attachments
    # add user message
    st.session_state.history.append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)

    # assistant answer
    with st.chat_message("assistant"):
        if streaming:
            answer = st.write_stream(
                chat_stream(
                    prompt,
                    system=st.session_state.system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=st.session_state.model,
                )
            )
        else:
            answer = chat_once(
                prompt,
                system=st.session_state.system,
                temperature=temperature,
                max_tokens=max_tokens,
                model=st.session_state.model,
            )
            st.markdown(answer)

    # persist to disk
    st.session_state.history.append(("assistant", answer))
    save_json(HISTORY_FILE, {"messages": st.session_state.history})
