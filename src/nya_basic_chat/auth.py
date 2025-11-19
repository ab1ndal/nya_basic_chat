# nya_basic_chat/auth.py
import streamlit as st
from supabase import create_client, Client
from nya_basic_chat.config import get_secret


def _sb() -> Client:
    SUPABASE_URL = get_secret("SUPABASE_URL")
    SUPABASE_ANON_KEY = get_secret("SUPABASE_ANON_KEY")
    if "sb_client" not in st.session_state:
        st.session_state.sb_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return st.session_state.sb_client


def _save_tokens(sess) -> None:
    try:
        access = getattr(sess, "access_token", None) or getattr(
            getattr(sess, "session", None), "access_token", None
        )
        refresh = getattr(getattr(sess, "session", None), "refresh_token", None)
        if access and refresh:
            st.session_state["_sb_tokens"] = {"access": access, "refresh": refresh}
    except Exception:
        pass


def _restore_tokens() -> None:
    tokens = st.session_state.get("_sb_tokens")
    if tokens:
        try:
            _sb().auth.set_session(tokens["access"], tokens["refresh"])
        except Exception:
            pass


def _is_allowed(email: str) -> bool:
    ALLOWED_DOMAIN = "nyase.com"
    return isinstance(email, str) and email.lower().strip().endswith("@" + ALLOWED_DOMAIN)


def sign_up_and_in() -> dict | None:
    """
    Renders a simple tabbed UI:
      • Sign up with email and password
      • Sign in with email and password
    Restricts access to nyase.com emails only.
    Returns a dict with user info when signed in, else None.
    """
    sb = _sb()
    _restore_tokens()

    existing = sb.auth.get_session()
    if existing and existing.user:
        return {"email": existing.user.email, "id": existing.user.id}

    st.title("Sign in")

    tabs = st.tabs(["Sign up", "Sign in"])

    with tabs[0]:
        su_email = st.text_input("Work email", key="su_email")
        su_pass = st.text_input("Password", type="password", key="su_pass")
        su_pass2 = st.text_input("Confirm password", type="password", key="su_pass2")
        if st.button("Create account"):
            if not _is_allowed(su_email):
                st.error("Use your nyase.com email")
            elif su_pass != su_pass2 or len(su_pass) < 8:
                st.error("Passwords must match and be at least 8 characters")
            else:
                try:
                    sb.auth.sign_up({"email": su_email, "password": su_pass})
                    st.success("Account created. Check your email to confirm before signing in")
                except Exception as e:
                    st.error(f"Sign up failed. {e}")

    with tabs[1]:
        si_email = st.text_input("Work email", key="si_email")
        si_pass = st.text_input("Password", type="password", key="si_pass")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Sign in"):
                if not _is_allowed(si_email):
                    st.error("Use your nyase.com email")
                else:
                    try:
                        sb.auth.sign_in_with_password({"email": si_email, "password": si_pass})
                        sess = sb.auth.get_session()
                        if not sess or not sess.user:
                            st.error("Sign in failed")
                        else:
                            st.session_state.sb_session = sess
                            st.success("Signed in")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Sign in failed. {e}")
        with col2:
            if st.button("Forget Password"):
                if not si_email:
                    st.warning("Enter your work email to reset your password")
                elif not _is_allowed(si_email):
                    st.error("Use your nyase.com email to reset your password")
                else:
                    try:
                        sb.auth.reset_password_for_email(
                            si_email,
                            options={
                                "redirect_to": "https://ab1ndal.github.io/reset-redirect-lightchat/reset.html"
                            },
                        )
                        st.success("A password reset email has been sent to your email")
                    except Exception as e:
                        st.error(f"Password reset failed. {e}")

    # return user if signed in
    try:
        sess = sb.auth.get_session()
        if sess and sess.user:
            return {"email": sess.user.email, "id": sess.user.id}
    except Exception:
        pass
    return None
