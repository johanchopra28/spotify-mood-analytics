"""Entry point: `streamlit run dashboard.py`. A top navigation bar switches between the pages."""
import streamlit as st

st.set_page_config(page_title="My Listening & Mood", page_icon=":material/headphones:", layout="wide")

navigation = st.navigation(
    [
        st.Page("pages/0_Dashboard.py", title="Dashboard", icon=":material/headphones:", default=True),
        st.Page("pages/1_Label_Comparison.py", title="Label Comparison", icon=":material/compare_arrows:"),
        st.Page("pages/2_Song_Lookup.py", title="Song Lookup", icon=":material/search:"),
    ],
    position="top",
)
navigation.run()
