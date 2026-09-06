"""
GoLegal UI - Copilot chat (sidebar drawer and full page)
"""
from __future__ import annotations

import streamlit as st

from ai.copilot import Copilot
from ai.llm import get_llm_client
from ai.tools import ToolContext
from ui import components as c
from ui.state import wizard_state


def _history() -> list:
    return st.session_state.setdefault("copilot_history", [])


def _run_turn(session, user, message: str) -> None:
    wiz = wizard_state()
    ctx = ToolContext(session=session, user=user, payload=wiz["payload"], agreement_id=wiz.get("agreement_id"))
    reply = Copilot(ctx).chat(_history(), message)
    hist = _history()
    hist.append({"role": "user", "content": message})
    hist.append({"role": "assistant", "content": reply.text, "actions": reply.actions, "suggestions": reply.suggestions, "mode": reply.mode})
    if reply.payload_changed:
        wiz["payload"] = reply.payload
        wiz["risk"] = None
        wiz["summary"] = None
        if wiz["step"] == 1:
            wiz["step"] = 2
    if ctx.agreement_id and not wiz.get("agreement_id"):
        wiz["agreement_id"] = ctx.agreement_id


def _render_thread(session, user, container, compact: bool) -> None:
    hist = _history()
    llm = get_llm_client()
    with container:
        if not hist:
            with st.chat_message("assistant", avatar="⚖️"):
                st.markdown("Hi, I'm **GoLegal Copilot**. Describe the tenancy in a sentence and I'll draft it, or ask me about "
                            "stamp duty, clauses, fair rent or who has signed.")
                if not compact:
                    st.caption(f"Model: {llm.model if llm.available else 'built-in rules (set ANTHROPIC_API_KEY for Claude)'}")
        for m in hist[-20:]:
            with st.chat_message(m["role"], avatar="⚖️" if m["role"] == "assistant" else "🧑"):
                st.markdown(m["content"])
                acts = m.get("actions") or []
                if acts and not compact:
                    with st.expander(f"{len(acts)} action(s) taken", expanded=False):
                        for a in acts:
                            st.markdown(f"<span class='gl-chat-action'>{'✔' if a.get('ok') else '✖'} {c.esc(a['tool'])} {c.esc(str(a.get('input'))[:120])}</span>", unsafe_allow_html=True)
                elif acts:
                    st.caption("Actions: " + ", ".join(a["tool"] for a in acts))
        last = hist[-1] if hist else None
        suggestions = (last or {}).get("suggestions") or (Copilot._default_suggestions() if not hist else [])
        if suggestions:
            cols = st.columns(min(len(suggestions), 2 if compact else 4))
            for i, s in enumerate(suggestions[: (2 if compact else 4)]):
                if cols[i % len(cols)].button(s[:60] + ("…" if len(s) > 60 else ""), key=f"sugg_{compact}_{i}_{len(hist)}", use_container_width=True):
                    _run_turn(session, user, s)
                    st.rerun()


def render_copilot_sidebar(session, user) -> None:
    with st.sidebar:
        st.markdown("<div style='display:flex;align-items:center;gap:.5rem'><span style='font-size:1.3rem'>⚖️</span><b>Copilot</b>"
                    "<span class='gl-pill info' style='margin-left:auto'>beta</span></div>", unsafe_allow_html=True)
        thread = st.container(height=420)
        _render_thread(session, user, thread, compact=True)
        prompt = st.chat_input("Ask or describe your agreement…", key="copilot_sidebar_input")
        if prompt:
            with st.spinner("Thinking…"):
                _run_turn(session, user, prompt)
            st.rerun()
        if _history() and st.button("Clear conversation", key="copilot_clear_side", use_container_width=True):
            st.session_state["copilot_history"] = []
            st.rerun()


def render_copilot_page(session, user) -> None:
    st.markdown("### Copilot")
    st.caption("A tool-using assistant over the same services the app uses. It can draft, price, review and track; "
               "payment and Aadhaar eSign always stay with you.")
    left, right = st.columns([1.6, 1], gap="large")
    with left:
        thread = st.container(height=520)
        _render_thread(session, user, thread, compact=False)
        prompt = st.chat_input("Ask or describe your agreement…", key="copilot_page_input")
        if prompt:
            with st.spinner("Thinking…"):
                _run_turn(session, user, prompt)
            st.rerun()
        if _history() and st.button("Clear conversation", key="copilot_clear_page"):
            st.session_state["copilot_history"] = []
            st.rerun()
    with right:
        wiz = wizard_state()
        p = wiz["payload"]
        st.markdown("**Live draft**")
        with st.container(border=True):
            c.kv({
                "Type": p.get("agreement_type", "").replace("_", " "), "State": p.get("state_code"),
                "Owners": ", ".join(o.get("name") for o in p.get("owners", []) if o.get("name")) or "—",
                "Tenants": ", ".join(t.get("name") for t in p.get("tenants", []) if t.get("name")) or "—",
                "Witnesses": ", ".join(w.get("name") for w in p.get("witnesses", []) if w.get("name")) or "—",
                "Property": ", ".join(x for x in [p.get("property", {}).get("premises_name"), p.get("property", {}).get("city")] if x) or "—",
                "Rent": c.money(p.get("commercials", {}).get("monthly_rent")), "Deposit": c.money(p.get("commercials", {}).get("security_deposit")),
                "Term": f"{p.get('commercials', {}).get('lease_months', 11)} months",
            })
            st.write("")
            if st.button("Open in wizard", type="primary", use_container_width=True):
                st.session_state["active_tab"] = "Create agreement"
                st.rerun()
        st.write("")
        st.markdown("**What Copilot can do**")
        st.markdown("""
- Draft from a sentence, a pasted contract or a PDF
- Compute stamp duty, fees and GST for any state
- Check fair rent and deposit norms for your locality
- Score clause risk and mask any identity numbers
- Explain terms; summarise in plain English or Hindi
- Track signatures and re-send links

**Never done by Copilot:** paying, buying e-Stamp paper, or signing on anyone's behalf.
""")
