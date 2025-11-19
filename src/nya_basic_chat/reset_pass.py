import streamlit as st


def handle_password_recovery():
    params = st.query_params

    if params.get("type") == "recovery":
        from nya_basic_chat.auth import _sb

        access = params.get("access_token")
        refresh = params.get("refresh_token")

        # Authenticate this temporary Supabase recovery session
        _sb().auth.set_session(access_token=access, refresh_token=refresh)

        st.subheader("Reset your password")

        pw1 = st.text_input("New password", type="password")
        pw2 = st.text_input("Confirm password", type="password")

        if st.button("Update password"):
            if pw1 != pw2:
                st.error("Passwords do not match")
            else:
                _sb().auth.update_user({"password": pw1})
                st.success("Password updated. Please sign in again.")
                st.stop()

        st.stop()
