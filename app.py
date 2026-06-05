"""BDO Alchemy Lab — standalone Streamlit app."""

import streamlit as st

st.set_page_config(
    page_title="Alchemy Lab",
    page_icon="⚗️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from alchemy.app import run_alchemy

run_alchemy()
