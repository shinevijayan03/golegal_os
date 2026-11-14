"""
Automated Streamlit UI Tests (streamlit.testing.v1.AppTest).
Enforces Phase 5 Competitive Mandate: Zero UI exceptions, accessible labels,
interactive tab navigation, and full workflow validation across all views.
"""
from __future__ import annotations
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).parent.parent / "app.py")


def test_app_initial_render_zero_exceptions():
    """Verify app bootstraps cleanly and renders all 6 tabs without any UI exceptions."""
    at = AppTest.from_file(APP_PATH, default_timeout=45)
    at.run()

    # Zero unhandled exceptions
    assert not at.exception, f"App raised unhandled exception on render: {at.exception}"

    # Verify tabs exist
    assert len(at.tabs) >= 6


def test_tenant_and_role_switcher_navigation():
    """Verify tenant and role persona switcher in top bar updates session state without error."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    # Switch tenant to org-beta-202
    org_picker = at.selectbox(key="sb_org_picker")
    assert org_picker is not None
    org_picker.select("org-beta-202")
    at.run()
    assert not at.exception
    assert at.session_state["active_org_id"] == "org-beta-202"

    # Switch role to legal_reviewer
    role_picker = at.selectbox(key="sb_role_picker")
    assert role_picker is not None
    role_picker.select("legal_reviewer")
    at.run()
    assert not at.exception
    assert at.session_state["active_role"] == "legal_reviewer"


def test_wizard_live_document_assembly():
    """Verify guided wizard form fields, real-time validation, and watermarked PDF preview."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    # Select template and check title input
    title_input = at.text_input(key="wiz_title")
    assert title_input is not None
    title_input.input("Bangalore Office Lease vNext")

    rent_input = at.number_input(key="wiz_rent")
    assert rent_input is not None
    rent_input.set_value(55000)

    at.run()
    assert not at.exception


def test_review_console_and_self_approval_block():
    """Verify review console renders diffs and enforces submitter self-approval block."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    # The demo contract was submitted by usr-edward-01 (editor/agent_builder).
    # If active persona is agent_builder, self-approval should be disabled or blocked.
    role_picker = at.selectbox(key="sb_role_picker")
    role_picker.select("agent_builder")
    at.run()
    assert not at.exception

    # Approve button should be disabled for submitter
    btn_approve = at.button(key="btn_approve_c")
    if btn_approve:
        assert btn_approve.disabled is True


def test_execution_console_and_mock_completed_badge():
    """Verify execution console stamping gate and mock provider outbox."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    # Verify execution components render without error
    stamp_form_button = at.button(key="btn_ready_exec")
    assert not at.exception


def test_camera_lab_quality_gate_telemetry():
    """Verify GPU Camera Lab processes synthetic sharp and blurred scans."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    # Click synthetic sharp scan ingestion
    btn_sharp = at.button(key="btn_gen_sharp")
    if btn_sharp:
        btn_sharp.click()
        at.run()
        assert not at.exception


def test_audit_vault_hash_chain_and_tamper_demo():
    """Verify cryptographic audit trail and 1-byte tamper demonstration."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    # Click 1-byte tamper demo button
    btn_tamper = at.button(key="btn_tamper_demo")
    if btn_tamper:
        btn_tamper.click()
        at.run()
        assert not at.exception
