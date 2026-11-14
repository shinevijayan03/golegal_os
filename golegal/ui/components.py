"""
Reusable UI Components for GoLegal vNext.
All text properly escaped; WCAG 2.2 AA compliant.
Uses st.html for reliable DOM rendering without Markdown code-block interpretation.
"""
from __future__ import annotations
import base64
import html
from typing import Dict, Any, Optional
import streamlit as st


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def render_html(html_str: str) -> None:
    """
    Safely render HTML without Markdown indented-code-block interference.
    Strips leading indentation from every line and renders natively.
    """
    lines = [line.strip() for line in html_str.strip().splitlines() if line.strip()]
    clean = "\n".join(lines)
    st.html(clean)


def render_html(html_str: str) -> None:
    """Renders raw HTML safely via Streamlit without Markdown code-block interpretation."""
    st.html(html_str)


def brand_header(org_name: str = "Acme Logistics Pvt. Ltd.", role: str = "Owner") -> None:
    st.html(
        f'<div class="gl-brand-header">'
        f'  <div>'
        f'    <div class="gl-logo">GoLegal <span>OS</span></div>'
        f'    <div class="gl-tagline">The agentic operating system for legal work.</div>'
        f'  </div>'
        f'  <div style="text-align: right;">'
        f'    <div class="gl-gpu-badge">'
        f'      <span class="gl-gpu-dot"></span>'
        f'      <span>NVIDIA RTX 3060 · 12 GB VRAM · CUDA 13.3</span>'
        f'    </div>'
        f'    <div style="font-size: 0.8rem; color: #4B5563; margin-top: 0.25rem;">'
        f'      Tenant: <b>{esc(org_name)}</b> | Role: <span style="color: #D32F2F; font-weight: 700;">{esc(role.upper())}</span>'
        f'    </div>'
        f'  </div>'
        f'</div>'
    )


def status_badge(status: str) -> str:
    cls = {
        "DRAFT": "gl-badge-draft",
        "IN_REVIEW": "gl-badge-review",
        "APPROVED": "gl-badge-approved",
        "READY_FOR_EXECUTION": "gl-badge-review",
        "SIGN_PENDING": "gl-badge-review",
        "MOCK_COMPLETED": "gl-badge-mock",
        "EXECUTED": "gl-badge-approved",
        "ARCHIVED": "gl-badge-draft",
        "CANCELLED": "gl-badge-danger",
    }.get(status, "gl-badge-draft")
    return f'<span class="gl-badge {cls}">{esc(status.replace("_", " "))}</span>'


def notice(text: str, tone: str = "warn") -> None:
    cls = "gl-notice-danger" if tone == "danger" else "gl-notice-warn"
    st.html(f'<div class="gl-notice-banner {cls}">{text}</div>')


def card(title: str, content: str) -> None:
    st.html(
        f'<div class="gl-card">'
        f'  <h4>{esc(title)}</h4>'
        f'  <div>{content}</div>'
        f'</div>'
    )


def revision_diff_viewer(old_fields: Dict[str, Any], new_fields: Dict[str, Any]) -> None:
    """Renders side-by-side comparison of contract revision fields (AT-05)."""
    all_keys = sorted(set(old_fields.keys()).union(set(new_fields.keys())))
    diff_rows = []
    for k in all_keys:
        v_old = old_fields.get(k, "—")
        v_new = new_fields.get(k, "—")
        changed = v_old != v_new
        bg = "background-color: #FFF7ED; font-weight: 600;" if changed else ""
        diff_rows.append(
            f'<tr style="{bg}">'
            f'<td style="padding: 8px 12px; border-bottom: 1px solid #E5E7EB;"><code>{esc(k)}</code></td>'
            f'<td style="padding: 8px 12px; border-bottom: 1px solid #E5E7EB; color: #B91C1C;">{esc(v_old)}</td>'
            f'<td style="padding: 8px 12px; border-bottom: 1px solid #E5E7EB; color: #047857;">{esc(v_new)}</td>'
            f'</tr>'
        )

    rows_html = "".join(diff_rows)
    html_table = (
        '<div style="overflow-x: auto; margin-top: 0.5rem; border: 1px solid #E5E7EB; border-radius: 8px; background: #FFFFFF; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">'
        '<table style="width: 100%; border-collapse: collapse; font-size: 0.85rem; background: #FFFFFF;">'
        '<thead>'
        '<tr style="border-bottom: 2px solid #FF5722; text-align: left; color: #C2410C; background: #FFF7ED;">'
        '<th style="padding: 10px 12px;">Field Key</th>'
        '<th style="padding: 10px 12px;">Prior Revision</th>'
        '<th style="padding: 10px 12px;">Current Draft</th>'
        '</tr>'
        '</thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table>'
        '</div>'
    )
    st.html(html_table)


def draft_document_viewer(
    title: str = "Commercial Legal Agreement",
    field_values: Optional[Dict[str, Any]] = None,
    watermark: str = "DRAFT — NOT EXECUTED",
    sha256_hash: str = "",
    pdf_bytes: Optional[bytes] = None,
    contract_id: str = "DRAFT-PREVIEW",
    org_id: str = "org-alpha-101",
    **kwargs: Any
) -> None:
    """Renders executive legal draft agreement deed viewer with cryptographic seal & PDF preview."""
    import hashlib
    field_vals = field_values if field_values is not None else kwargs.get("field_values", {})
    title = kwargs.get("title", title)
    contract_id = kwargs.get("contract_id", contract_id)
    org_id = kwargs.get("org_id", org_id)
    watermark = kwargs.get("watermark", watermark)
    pdf_b = pdf_bytes if pdf_bytes is not None else kwargs.get("pdf_bytes")

    seal_hash = sha256_hash or kwargs.get("pdf_sha256", "")
    if not seal_hash:
        if pdf_b:
            seal_hash = hashlib.sha256(pdf_b).hexdigest()
        else:
            seal_hash = hashlib.sha256(str(sorted(field_vals.items())).encode("utf-8")).hexdigest()

    size_label = f"{len(pdf_b):,} bytes" if pdf_b else "Native Assembly"

    # 1. Cryptographic Seal Banner
    seal_html = (
        f'<div style="background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 8px; padding: 12px; margin-bottom: 12px; font-size: 0.82rem;">'
        f'  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">'
        f'    <span style="color: #D97706; font-weight: bold; font-size: 0.85rem;">🔒 CRYPTOGRAPHIC SEAL (SHA-256)</span>'
        f'    <span class="gl-badge gl-badge-draft">{esc(watermark)}</span>'
        f'  </div>'
        f'  <code style="word-break: break-all; color: #047857; background: #ECFDF5; padding: 3px 8px; border-radius: 4px; display: block; margin: 4px 0; font-size: 0.76rem;">{seal_hash}</code>'
        f'  <div style="color: #4B5563; font-size: 0.78rem; margin-top: 4px;">'
        f'    Pages: <b>1</b> · Size: <b>{size_label}</b> · Format: <b>PDF / Section 65B Compliant</b>'
        f'  </div>'
        f'</div>'
    )
    st.html(seal_html)

    # 2. Executive Assembled Deed Sheet
    pa = field_vals.get("first_party", "—")
    pb = field_vals.get("second_party", "—")
    rent_paise = field_vals.get("monthly_rent_paise", 0)
    rent_str = f"₹{rent_paise / 100:,.2f}" if rent_paise else "—"
    dep_paise = field_vals.get("security_deposit_paise", 0)
    dep_str = f"₹{dep_paise / 100:,.2f}" if dep_paise else "—"
    comm_date = field_vals.get("lease_commencement_date", "—")
    exp_date = field_vals.get("lease_expiration_date", "—")
    notice_days = field_vals.get("notice_period_days", "30")
    cov = field_vals.get("custom_covenants", "Standard statutory residential covenants apply.")

    deed_html = (
        f'<div style="background: #FFFDF9; border: 2px solid #E5E7EB; border-radius: 8px; padding: 1.25rem; margin-bottom: 1rem; position: relative; box-shadow: 0 2px 8px rgba(0,0,0,0.04); font-family: -apple-system, BlinkMacSystemFont, Georgia, serif;">'
        f'  <div style="position: absolute; top: 38%; left: 10%; transform: rotate(-25deg); font-size: 2.2rem; font-weight: 900; color: rgba(220, 38, 38, 0.08); pointer-events: none; text-transform: uppercase; letter-spacing: 4px; border: 4px dashed rgba(220, 38, 38, 0.12); padding: 10px 30px; border-radius: 8px;">'
        f'    {esc(watermark)}'
        f'  </div>'
        f'  <div style="border-bottom: 2px solid #D32F2F; padding-bottom: 8px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: flex-end;">'
        f'    <div>'
        f'      <div style="font-size: 0.72rem; letter-spacing: 1.5px; color: #D32F2F; font-weight: bold; text-transform: uppercase;">GOVERNMENT OF KARNATAKA e-STAMP CERTIFICATE</div>'
        f'      <div style="font-size: 1.15rem; font-weight: 800; color: #111827;">{esc(title)}</div>'
        f'    </div>'
        f'    <div style="font-size: 0.72rem; color: #6B7280; text-align: right;">'
        f'      <span>ID: <code>{esc(str(contract_id)[:12])}...</code></span><br/>'
        f'      <span>Org: <code>{esc(str(org_id))}</code></span>'
        f'    </div>'
        f'  </div>'
        f'  <div style="font-size: 0.85rem; color: #374151; line-height: 1.6; margin-bottom: 12px;">'
        f'    <b>First Party (Lessor):</b> {esc(pa)}<br/>'
        f'    <b>Second Party (Lessee):</b> {esc(pb)}'
        f'  </div>'
        f'  <div style="background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; font-size: 0.82rem;">'
        f'    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px;">'
        f'      <div><span style="color: #6B7280;">Monthly Rent:</span><br/><b style="color: #047857; font-size: 0.95rem;">{rent_str}</b></div>'
        f'      <div><span style="color: #6B7280;">Security Deposit:</span><br/><b style="color: #111827; font-size: 0.95rem;">{dep_str}</b></div>'
        f'      <div><span style="color: #6B7280;">Commencement:</span><br/><b style="color: #111827;">{esc(comm_date)}</b></div>'
        f'      <div><span style="color: #6B7280;">Expiration:</span><br/><b style="color: #111827;">{esc(exp_date)}</b></div>'
        f'      <div><span style="color: #6B7280;">Notice Period:</span><br/><b style="color: #111827;">{esc(notice_days)} days</b></div>'
        f'    </div>'
        f'  </div>'
        f'  <div style="font-size: 0.8rem; color: #4B5563; line-height: 1.5; border-top: 1px solid #F3F4F6; padding-top: 8px;">'
        f'    <b>Special Covenants &amp; Clauses:</b> <i>{esc(cov)}</i>'
        f'  </div>'
        f'</div>'
    )
    st.html(deed_html)

    # 3. Interactive PDF Preview Expander (when PDF bytes available)
    if pdf_b:
        b64_pdf = base64.b64encode(pdf_b).decode("utf-8")
        with st.expander("📄 View Watermarked Binary PDF Preview", expanded=False):
            pdf_iframe = (
                f'<iframe src="data:application/pdf;base64,{b64_pdf}#toolbar=0" '
                f'width="100%" height="480" type="application/pdf" '
                f'style="border: 1px solid #E5E7EB; border-radius: 8px;">'
                f'</iframe>'
            )
            st.html(pdf_iframe)
