import streamlit as st


@st.cache_resource
def load_bridge():
    try:
        from twin_adapter import TwinBridge
        return TwinBridge()
    except Exception as e:
        return f"{type(e).__name__}: {e}"