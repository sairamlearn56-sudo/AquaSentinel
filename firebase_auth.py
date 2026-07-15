import pyrebase
import streamlit as st

firebase_config = {
    "apiKey": st.secrets["firebase_web"]["apiKey"],
    "authDomain": st.secrets["firebase_web"]["authDomain"],
    "projectId": st.secrets["firebase_web"]["projectId"],
    "storageBucket": st.secrets["firebase_web"]["storageBucket"],
    "messagingSenderId": st.secrets["firebase_web"]["messagingSenderId"],
    "appId": st.secrets["firebase_web"]["appId"],
    "databaseURL": st.secrets["firebase"]["database_url"]
}

firebase = pyrebase.initialize_app(firebase_config)
auth = firebase.auth()

def login_user(email, password):
    return auth.sign_in_with_email_and_password(email, password)

def signup_user(email, password):
    return auth.create_user_with_email_and_password(email, password)
