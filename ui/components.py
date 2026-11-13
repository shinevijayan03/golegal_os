"""
Reusable GoLegal UI components (HTML rendered through the design system in ui/theme.py).
All user-provided text is escaped before it is placed into markup.
"""
from __future__ import annotations

import html
from typing import Any, Dict, Iterable, List, Optional

import streamlit as st

from services.rule_engine import AGREEMENT_TYPE_LABELS, STATE_STAMP_RULES
from services.validation import safe_mask_aadhaar


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def money(value: Any) -> str:
    try:
        return f"₹{float(value):,.0f}"
    except (TypeError, ValueError):
        return "₹0"


def brand(tagline: str = "The agentic operating system for legal work.") -> None:
    st.markdown(f"""
    <div class="gl-brand gl-fade">
      <div class="mark">G</div>
      <div class="name">GoLegal OS</div>
      <span class="tag">{esc(tagline)}</span>
    </div>""", unsafe_allow_html=True)


def eyebrow(text: str) -> None:
    st.markdown(f'<div class="gl-eyebrow">{esc(text)}</div>', unsafe_allow_html=True)


def display(text_html: str, lede: Optional[str] = None) -> None:
    lede_html = f'<p class="gl-lede">{esc(lede)}</p>' if lede else ""
    st.markdown(f'<div class="gl-fade"><h1 class="gl-display">{text_html}</h1>{lede_html}</div>', unsafe_allow_html=True)


def status_pill(status: str, label: Optional[str] = None) -> str:
    cls = {"Draft": "draft", "Paid": "paid", "Pending_Signatures": "pending", "Completed": "completed", "Signed": "signed",
           "Pending": "pending", "Sent": "pending", "Expired": "expired", "Cancelled": "cancelled", "Rejected": "danger"}.get(status, "info")
    return f'<span class="gl-pill {cls}"><span class="dot"></span>{esc(label or status.replace("_", " "))}</span>'


def stat(label: str, value: str, sub: str = "", tone: str = "", mono: bool = False) -> None:
    st.markdown(f"""<div class="gl-stat {tone}"><div class="k">{esc(label)}</div>
    <div class="v {'mono' if mono else ''}">{esc(value)}</div><div class="s">{esc(sub)}</div></div>""", unsafe_allow_html=True)


def card(title: str, body: str, accent: bool = False) -> None:
    st.markdown(f'<div class="gl-card {"accent" if accent else ""} gl-fade"><h4>{esc(title)}</h4><p>{esc(body)}</p></div>',
                unsafe_allow_html=True)


def notice(text: str, tone: str = "info") -> None:
    st.markdown(f'<div class="gl-notice {tone}">{text}</div>', unsafe_allow_html=True)


def empty_state(icon: str, title: str, body: str) -> None:
    st.markdown(f'<div class="gl-empty"><div class="i">{icon}</div><div class="t">{esc(title)}</div><div>{esc(body)}</div></div>',
                unsafe_allow_html=True)


def trust_strip() -> None:
    st.markdown("""<div class="gl-trust gl-fade">
      <span>IT Act 2000 §§ 4, 5, 10A</span><span>Indian Evidence Act § 65B certificate</span>
      <span>StockHolding (SHCIL) e-Stamp</span><span>UIDAI Aadhaar eSign</span><span>AES-256 at rest · TLS 1.3</span>
    </div>""", unsafe_allow_html=True)


def stepper(current: int, labels: Iterable[str]) -> None:
    cells = []
    for i, label in enumerate(labels, 1):
        cls = "active" if i == current else "done" if i < current else ""
        cells.append(f'<div class="gl-step {cls}"><div class="n">STEP {i:02d}</div><div class="t">{esc(label)}</div></div>')
    st.markdown(f'<div class="gl-stepper">{"".join(cells)}</div>', unsafe_allow_html=True)


def party_row(name: str, role: str, aadhaar_masked: Optional[str], status: str, extra: str = "") -> str:
    return (f'<div class="gl-party"><div><div class="nm">{esc(name)}</div><div class="rl">{esc(role)} '
            f'<span class="aad">{esc(aadhaar_masked or "")}</span></div></div><div>{status_pill(status)} {extra}</div></div>')


def progress_seal(signed: int, total: int) -> None:
    pct = int(100 * signed / total) if total else 0
    color = "#059669" if total and signed == total else "#1E3A8A"
    st.markdown(f"""
    <div class="gl-progress-seal">
      <div class="gl-ring {'done' if total and signed == total else ''}" style="background: conic-gradient({color} {pct}%, #E2E8F0 0);">
        <div class="in">{signed}/{total}</div></div>
      <div><div style="font-weight:700;color:#0F172A">{"Sealed and certified" if total and signed == total else "Signatures collected"}</div>
      <div style="font-size:.85rem;color:#64748B">{"All parties have signed. The corporate seal is applied." if total and signed == total else "Parties sign independently, in any order, from their own devices."}</div></div>
    </div>""", unsafe_allow_html=True)


def risk_panel(report: Dict[str, Any]) -> None:
    level = report.get("level", "low")
    tone = {"high": "danger", "medium": "warn", "low": "ok"}.get(level, "info")
    notice(f"<b>Clause risk {esc(level.upper())}</b> · score {esc(report.get('score', 0))}/100 · {esc(report.get('summary', ''))}", tone)
    for f in report.get("findings", []):
        quote = f'<div class="q">“{esc(f.get("quote"))}”</div>' if f.get("quote") else ""
        st.markdown(f"""<div class="gl-risk {esc(f.get('severity', 'info'))}"><div class="t">{esc(f.get('title'))}
        <span class="gl-pill {'danger' if f.get('severity') == 'high' else 'pending' if f.get('severity') == 'medium' else 'info'}">{esc(f.get('severity'))}</span></div>
        {quote}<div class="d">{esc(f.get('detail'))}</div><div class="s">→ {esc(f.get('suggestion'))}</div></div>""", unsafe_allow_html=True)


def deed_preview(payload: Dict[str, Any], clauses: List[Dict[str, Any]], estamp: Optional[Dict[str, Any]] = None,
                 parties_status: Optional[List[Dict[str, Any]]] = None, sealed: bool = False, quote: Optional[Dict[str, Any]] = None) -> None:
    """The agreement rendered as e-Stamp paper - the product's signature surface."""
    prop = payload.get("property", {})
    c = payload.get("commercials", {})
    state = payload.get("state_code", "KA")
    state_name = STATE_STAMP_RULES.get(state, {}).get("name", state)
    owners = [o for o in payload.get("owners", []) if o.get("name")]
    tenants = [t for t in payload.get("tenants", []) if t.get("name")]
    witnesses = [w for w in payload.get("witnesses", []) if w.get("name")]
    duty = (estamp or {}).get("stamp_amount") or (quote or {}).get("stamp_duty_amount", 100)
    cert = (estamp or {}).get("certificate_number", "DRAFT - NOT YET PROCURED")
    title = AGREEMENT_TYPE_LABELS.get(payload.get("agreement_type", "Rental_Residential"), "Agreement").upper()
    seal_cls, seal_txt = ("sealed", "SEALED · SECTION 65B") if sealed else ("", "DRAFT · NOT EXECUTED")

    def names(group):
        return ", ".join(esc(p["name"]) for p in group) or "—"

    def party_lines(label, group):
        out = []
        for i, p in enumerate(group, 1):
            sfx = f" {i}" if len(group) > 1 else ""
            details = ", ".join(x for x in [
                f"PAN {esc(p['pan'])}" if p.get("pan") else "", f"Aadhaar {esc(safe_mask_aadhaar(p['aadhaar']))}" if p.get("aadhaar") else "",
                esc(p.get("phone")), esc(p.get("email"))] if x)
            out.append(f'<p><b>{label}{sfx}:</b> {esc(p["name"])}{", " + details if details else ""}</p>')
        return "".join(out) or f"<p><b>{label}:</b> —</p>"

    clause_html = "".join(f'<div class="clause"><b>{i}. {esc(cl["title"])}.</b> {esc(cl["text"])}</div>' for i, cl in enumerate(clauses, 1))
    custom = payload.get("custom_clauses", "").strip()
    if custom:
        clause_html += f'<div class="clause"><b>{len(clauses) + 1}. Additional covenants.</b> {esc(custom)}</div>'

    sig_html = ""
    if parties_status:
        cells = []
        for p in parties_status:
            if p.get("status") == "Signed":
                cells.append(f'<div class="sig"><div class="who">{esc(p["name"])}</div><div>{esc(p["type"])} · Aadhaar eSign</div><div class="hash">{esc(p.get("hash", ""))[:24]}…</div></div>')
            else:
                cells.append(f'<div class="sig"><div class="who">{esc(p["name"])}</div><div>{esc(p["type"])}</div><div class="wait">Awaiting signature</div></div>')
        sig_html = f'<div class="sigs">{"".join(cells)}</div>'
    else:
        sig_html = '<div class="sigs">' + "".join(
            f'<div class="sig"><div class="who">{esc(p["name"])}</div><div>{role}</div><div class="wait">Signs via Aadhaar OTP</div></div>'
            for role, group in (("Lessor", owners), ("Lessee", tenants), ("Witness", witnesses)) for p in group) + "</div>"

    rent = float(c.get("monthly_rent") or 0)
    dep = float(c.get("security_deposit") or 0)
    st.markdown(f"""
    <div class="gl-deed gl-fade">
      <div class="gl-seal {seal_cls}">{seal_txt}</div>
      <div class="cert">
        <div class="h">GOVERNMENT OF {esc(state_name).upper()} · e-STAMP CERTIFICATE</div>
        <div class="g">
          <div><b>Certificate No.</b> <span class="mono">{esc(cert)}</span></div><div><b>Stamp duty</b> {money(duty)}</div>
          <div><b>First party</b> {names(owners)}</div><div><b>Second party</b> {names(tenants)}</div>
          <div><b>Article</b> {esc(STATE_STAMP_RULES.get(state, {}).get('article', 'Lease'))}</div><div><b>Vendor</b> StockHolding Corporation of India</div>
        </div>
      </div>
      <h3 class="t">{esc(title)}</h3>
      <p>This deed is made at {esc(prop.get('city') or state_name)} between the parties described below, on e-Stamp paper of {esc(state_name)}, and executed electronically under the Information Technology Act, 2000.</p>
      {party_lines("Lessor / Owner", owners)}
      {party_lines("Lessee / Tenant", tenants)}
      <div class="schedule"><b>Schedule.</b> {esc(prop.get('premises_name') or 'Premises')}, {esc(prop.get('address') or '—')}, {esc(prop.get('city') or '')} {esc(prop.get('pincode') or '')}.
        {('Inclusions: ' + esc(prop.get('inclusions')) + '.') if prop.get('inclusions') else ''}<br/>
        Rent <b>{money(rent)}</b> per month payable by the {esc(c.get('rent_due_day', 5))}th · Deposit <b>{money(dep)}</b> (refundable) ·
        Term <b>{esc(c.get('lease_months', 11))} months</b>{(' from ' + esc(c.get('lease_start'))) if c.get('lease_start') else ''} ·
        Lock-in {esc(c.get('lock_in_months', 0))} months · Notice {esc(c.get('notice_days', 30))} days · Escalation {esc(c.get('escalation_pct', 5))}% on renewal.
      </div>
      {clause_html}
      {sig_html}
    </div>""", unsafe_allow_html=True)


def kv(pairs: Dict[str, Any]) -> None:
    st.markdown('<div class="gl-kv">' + "".join(f"<b>{esc(k)}</b><span>{esc(v)}</span>" for k, v in pairs.items()) + "</div>",
                unsafe_allow_html=True)


def how_it_works() -> None:
    steps = [
        ("1", "Describe the tenancy", "Type it, paste an old agreement, or fill the form. Copilot drafts the deed on lawyer-vetted clauses and flags anything unfair."),
        ("2", "Pay once, stamped instantly", "One payment covers state stamp duty and the platform fee. The e-Stamp certificate from StockHolding becomes page one of your deed."),
        ("3", "Everyone signs from their phone", "Each party gets a private link and signs with Aadhaar OTP - in any order, from anywhere. GoLegal OS seals the deed and issues the Section 65B certificate."),
    ]
    st.markdown('<div class="gl-how gl-fade">' + "".join(
        f'<div class="st"><div class="n">{n}</div><div class="t">{esc(t)}</div><p>{esc(p)}</p></div>' for n, t, p in steps) + "</div>",
        unsafe_allow_html=True)
