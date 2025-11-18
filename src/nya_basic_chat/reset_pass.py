import streamlit as st
import urllib.parse
from nya_basic_chat.auth import _sb


def _inject_capture_script():
    st.components.v1.html(
        """
        <script>
        const hash = window.location.hash;
        if (hash && hash.includes("recovery")) {
            localStorage.setItem("supabase_recovery_data", hash);
        }
        </script>
        """,
        height=0,
    )


def _inject_send_script():
    st.components.v1.html(
        """
        <script>
        const data = localStorage.getItem("supabase_recovery_data");
        if (data) {
            window.parent.postMessage(
                {type: "supabase-recovery", data: data},
                "*"
            );
        }
        </script>
        """,
        height=0,
    )


def _capture_post_message():
    try:
        ctx = st.runtime.scriptrunner.script_run_context.get_script_run_ctx()
        if ctx and ctx.msg_queue:
            for m in ctx.msg_queue:
                if isinstance(m, dict) and m.get("type") == "supabase-recovery":
                    st.session_state["supabase_recovery_data"] = m["data"]
    except Exception:
        pass


def _parse_fragment():
    fragment = st.session_state.get("supabase_recovery_data")
    if not fragment:
        return {}

    if fragment.startswith("#"):
        clean = fragment.lstrip("#")
        parsed = urllib.parse.parse_qs(clean)
        return {k: v[0] for k, v in parsed.items()}

    return {}


def handle_password_recovery():
    _inject_capture_script()
    _inject_send_script()
    _capture_post_message()

    recovery_params = _parse_fragment()
    mode = recovery_params.get("type")

    if mode != "recovery":
        return  # Do nothing unless in recovery mode

    st.subheader("Reset your password")

    access_token = recovery_params.get("access_token")
    refresh_token = recovery_params.get("refresh_token")

    try:
        _sb().auth.set_session(access_token=access_token, refresh_token=refresh_token)
    except Exception as e:
        st.error(f"Unable to initialize session: {e}")

    new_pw = st.text_input("New password", type="password")
    confirm_pw = st.text_input("Confirm password", type="password")

    if st.button("Update password"):
        if new_pw != confirm_pw:
            st.error("Passwords do not match")
        else:
            try:
                _sb().auth.update_user({"password": new_pw})
                st.success("Password updated. Please sign in again.")

                st.components.v1.html(
                    "<script>localStorage.removeItem('supabase_recovery_data'); "
                    "window.location.hash='';</script>",
                    height=0,
                )
                st.rerun()
            except Exception as e:
                st.error(f"Failed to update password: {e}")

    st.stop()  # Stop the rest of the app from rendering during reset flow
