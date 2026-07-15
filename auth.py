import streamlit as st

def login():
    st.title("🔐 AquaSentinel Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if email and password:
            st.session_state["logged_in"] = True
            st.session_state["user_email"] = email
            st.success("Login successful")
            st.rerun()
        else:
            st.error("Enter email and password")

def logout():
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()
