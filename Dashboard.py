import streamlit as st

st.set_page_config(
    page_title="WikiProject Medicine Article Recommender",
    page_icon="🔬",
    layout="wide",
)

pg = st.navigation([
    st.Page("pages/Home.py",             title="WikiMed Dashboard", icon="🔬", default=True),
    st.Page("pages/Cancer_Dashboard.py", title="Cancer Dashboard",  icon="🎗️"),
    st.Page("pages/Methodology.py",      title="Methodology",       icon="📖"),
])
pg.run()
