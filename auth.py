import streamlit as st

def login():
    st.title("🔐 AquaSentinel Login")

   tab1, tab2, tab3 = st.tabs([
    "📧 Email",
    "🔵 Google",
    "📱 Phone OTP"
])

with tab1:
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login with Email"):
        if email and password:
            st.session_state["logged_in"] = True
            st.session_state["user_email"] = email
            st.success("Login successful")
            st.rerun()
        else:
            st.error("Enter email and password")

with tab2:
    st.info("Google Sign-In will be connected in the next step.")
    st.button("Continue with Google")

with tab3:
    phone = st.text_input("Phone Number (+91...)")
    otp = st.text_input("OTP")

    col1, col2 = st.columns(2)

    with col1:
        st.button("Send OTP")

    with col2:
        st.button("Verify OTP")
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
