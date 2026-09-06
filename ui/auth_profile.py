"""
GoLegal UI - Authentication, Profile & Suspicious Ingress Simulation
"""
import streamlit as st
from services.validation import validate_phone, validate_email


def render_auth_profile():
    st.header("👤 User Account & Security Center")

    user = st.session_state.get("authenticated_user")

    col1, col2 = st.columns([1.2, 1], gap="large")

    with col1:
        if user:
            st.subheader(f"Welcome, {user.get('name', 'User')}")
            with st.container(border=True):
                st.markdown(f"""
                - **Role**: `{user.get('role', 'Single_User')}`
                - **Email**: `{user.get('email', 'N/A')}`
                - **Phone**: `{user.get('phone', 'N/A')}`
                - **Session Security**: `AES-256 TLS 1.3 Active`
                """)

                c1, c2 = st.columns(2)
                with c1:
                    new_role = st.selectbox("Switch Persona / View:", ["Tenant", "Owner", "Admin"], index=["Tenant", "Owner", "Admin"].index(user.get("role", "Tenant")))
                    if new_role != user.get("role"):
                        user["role"] = new_role
                        st.session_state["authenticated_user"] = user
                        st.success(f"Switched active persona to {new_role}")
                        st.rerun()
                with c2:
                    if st.button("🚪 Sign Out", use_container_width=True):
                        st.session_state["authenticated_user"] = None
                        st.rerun()

        else:
            st.subheader("🔑 Sign In / Quick Guest Access")
            auth_mode = st.radio("Authentication Method:", ["Mobile OTP (Mock)", "Password Sign-In", "Switch to Demo Persona"], horizontal=True)

            if auth_mode == "Mobile OTP (Mock)":
                mobile = st.text_input("Enter 10-Digit Mobile Number:", value="9876543210")
                if "otp_sent" not in st.session_state:
                    st.session_state["otp_sent"] = False

                if not st.session_state["otp_sent"]:
                    if st.button("📲 Send OTP", type="primary"):
                        if validate_phone(mobile):
                            st.session_state["otp_sent"] = True
                            st.session_state["active_otp"] = "123456"
                            st.info("Mock OTP sent to mobile: **123456** (Expires in 5 mins)")
                            st.rerun()
                        else:
                            st.error("Please enter a valid 10-digit Indian mobile number")
                else:
                    otp_input = st.text_input("Enter 6-Digit OTP:", value="123456")
                    if st.button("✅ Verify & Sign In", type="primary"):
                        if otp_input == st.session_state.get("active_otp"):
                            st.session_state["authenticated_user"] = {
                                "id": "usr-tenant-001",
                                "name": "Mayank Tripathi",
                                "email": "mayank.tripathi@example.com",
                                "phone": mobile,
                                "role": "Tenant",
                                "is_admin": False
                            }
                            st.session_state["otp_sent"] = False
                            st.success("Successfully authenticated!")
                            st.rerun()
                        else:
                            st.error("Invalid OTP. Try entering 123456")

            elif auth_mode == "Switch to Demo Persona":
                persona = st.selectbox("Select Demo Profile:", [
                    "Mayank Tripathi (Tenant)",
                    "Ramakiran Reddy (Owner / Landlord)",
                    "Administrator (Operations & Finance)"
                ])
                if st.button("🚀 Load Persona Session", type="primary"):
                    if "Tenant" in persona:
                        st.session_state["authenticated_user"] = {
                            "id": "usr-tenant-001",
                            "name": "Mayank Tripathi",
                            "email": "mayank.tripathi@example.com",
                            "phone": "9876543211",
                            "role": "Tenant",
                            "is_admin": False
                        }
                    elif "Owner" in persona:
                        st.session_state["authenticated_user"] = {
                            "id": "usr-owner-001",
                            "name": "Ramakiran Reddy",
                            "email": "ramakiran.reddy@example.com",
                            "phone": "9876543210",
                            "role": "Owner",
                            "is_admin": False
                        }
                    else:
                        st.session_state["authenticated_user"] = {
                            "id": "usr-admin-001",
                            "name": "GoLegal Operations Admin",
                            "email": "admin@golegal.in",
                            "phone": "9876543299",
                            "role": "Admin",
                            "is_admin": True
                        }
                    st.success(f"Loaded profile: {persona}")
                    st.rerun()

            else:
                email = st.text_input("Email:", "mayank.tripathi@example.com")
                pwd = st.text_input("Password:", "••••••••", type="password")
                if st.button("Sign In", type="primary"):
                    st.session_state["authenticated_user"] = {
                        "id": "usr-tenant-001",
                        "name": "Mayank Tripathi",
                        "email": email,
                        "phone": "9876543211",
                        "role": "Tenant",
                        "is_admin": False
                    }
                    st.success("Signed in successfully!")
                    st.rerun()

    with col2:
        st.subheader("🛡️ Suspicious Ingress & Anomaly Simulation")
        with st.container(border=True):
            st.markdown("""
            **Automated Ingress Protection**:
            GoLegal evaluates incoming HTTP requests against user profile history (IP subnet, browser fingerprint, device type).
            """)

            if st.button("🚨 Simulate Suspicious Device / IP Login", type="secondary"):
                st.session_state["suspicious_login_alert"] = {
                    "ip": "198.51.100.24",
                    "device": "Unknown Linux x86_64 / Headless Chrome",
                    "location": "Bucharest, Romania",
                    "timestamp": "Just now",
                    "risk_level": "CRITICAL"
                }
                st.rerun()

            alert = st.session_state.get("suspicious_login_alert")
            if alert:
                st.error(f"""
                ⚠️ **SUSPICIOUS LOGIN ALERT DISPATCHED**
                - **Originating IP**: `{alert['ip']}`
                - **Device Fingerprint**: `{alert['device']}`
                - **Geo-Location**: `{alert['location']}`
                - **Action Taken**: Security alert email dispatched to user; MFA challenge enforced.
                """)
                if st.button("Clear Alert"):
                    st.session_state["suspicious_login_alert"] = None
                    st.rerun()
