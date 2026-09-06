"""
GoLegal Digital Contracting Web Application - Main Entry Point
Streamlit multi-page application complying with IT Act 2000, Section 65B, and 5-layer architecture.
"""
import streamlit as st
from streamlit_option_menu import option_menu
from persistence.database import init_db
from ui.landing import render_landing_page
from ui.wizard import render_wizard
from ui.dashboard import render_dashboard
from ui.admin import render_admin
from ui.auth_profile import render_auth_profile

# Set Streamlit Page Configuration
st.set_page_config(
    page_title="GoLegal | Digital Contracting & e-Stamping",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Database Schema & Seed Defaults
init_db()

# Custom CSS for Trust & High Contrast Legal UI
st.markdown("""
<style>
    /* Primary buttons */
    .stButton>button[kind="primary"] {
        background-color: #1E3A8A;
        color: #FFFFFF;
        font-weight: 600;
        border-radius: 6px;
    }
    /* Headers */
    h1, h2, h3 {
        color: #1E3A8A;
        font-family: 'Inter', -apple-system, sans-serif;
    }
    /* Footer watermark */
    footer {visibility: hidden;}
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# Session State Initialization
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "Home"

if "authenticated_user" not in st.session_state:
    st.session_state["authenticated_user"] = {
        "id": "usr-tenant-001",
        "name": "Mayank Tripathi",
        "email": "mayank.tripathi@example.com",
        "phone": "9876543211",
        "role": "Tenant",
        "is_admin": False
    }

user = st.session_state["authenticated_user"]

# Top Navbar with User Indicator
col_logo, col_user = st.columns([3, 1.2])
with col_logo:
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 0.5rem;">
        <span style="font-size: 1.8rem;">⚖️</span>
        <span style="font-size: 1.5rem; font-weight: 800; color: #1E3A8A; letter-spacing: -0.5px;">GoLegal</span>
        <span style="background: #D1FAE5; color: #065F46; font-size: 0.75rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 12px; margin-left: 0.5rem;">
            INDIA PRODUCTION BASELINE
        </span>
    </div>
    """, unsafe_allow_html=True)

with col_user:
    if user:
        st.markdown(f"""
        <div style="text-align: right; font-size: 0.85rem; color: #475569; padding-top: 0.3rem;">
            Active Actor: <b>{user.get('name')}</b> ({user.get('role')})
        </div>
        """, unsafe_allow_html=True)

# Primary Navigation Menu
tabs = ["Home", "Create Agreement", "Dashboard", "Admin Console", "Profile & Security"]
icons = ["house", "file-earmark-text", "kanban", "gear", "person-circle"]

current_index = tabs.index(st.session_state["active_tab"]) if st.session_state["active_tab"] in tabs else 0

selected = option_menu(
    menu_title=None,
    options=tabs,
    icons=icons,
    default_index=current_index,
    orientation="horizontal",
    styles={
        "container": {"padding": "0!important", "background-color": "#F8FAFC", "border-bottom": "1px solid #E2E8F0"},
        "icon": {"color": "#1E3A8A", "font-size": "14px"},
        "nav-link": {
            "font-size": "14px",
            "text-align": "center",
            "margin": "0px",
            "padding": "10px 15px",
            "--hover-color": "#E2E8F0",
            "color": "#334155"
        },
        "nav-link-selected": {
            "background-color": "#1E3A8A",
            "color": "white",
            "font-weight": "600"
        },
    }
)

if selected != st.session_state["active_tab"]:
    st.session_state["active_tab"] = selected
    st.rerun()

# Route views based on active selection
active_tab = st.session_state["active_tab"]

if active_tab == "Home":
    render_landing_page()
elif active_tab == "Create Agreement":
    render_wizard()
elif active_tab == "Dashboard":
    render_dashboard()
elif active_tab == "Admin Console":
    render_admin()
elif active_tab == "Profile & Security":
    render_auth_profile()
