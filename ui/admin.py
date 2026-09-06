"""
GoLegal UI - Platform operations console

Stamping treasury, GMV and funnel analytics, the autonomous workflow agent,
user administration, template library, NPS console and the evidentiary audit journal.
"""
from __future__ import annotations

import json
from collections import Counter

import pandas as pd
import streamlit as st

from ai.workflow_agent import WorkflowAgent
from domain.models import (
    AgentRun, Agreement, AuditLog, Feedback, LoginEvent, Notification, Payment, SysConfig, SysConfigJn, User,
)
from services.rule_engine import OPTIONAL_TOGGLES, STATE_STAMP_RULES, get_default_clauses
from services.stamping_service import StampingService
from ui import components as c


def _treasury(session, stamping: StampingService) -> None:
    balance = stamping.get_prepaid_balance()
    threshold = stamping.get_threshold()
    low = stamping.is_low_balance()

    if low:
        c.notice(f"<b>Critical: SHCIL prepaid balance is {c.money(balance)}</b>, below the {c.money(threshold)} threshold. "
                 "Stamping calls will fail once the pool is exhausted. Replenish now.", "danger")

    cols = st.columns([1, 1, 1, 1.4])
    with cols[0]:
        c.stat("SHCIL prepaid balance", c.money(balance), "live corporate pool", tone="danger" if low else "ok")
    debits = [j for j in session.query(SysConfigJn).all() if "debited" in (j.new_value or "")]
    total_debited = sum(json.loads(j.new_value).get("debited", 0) for j in debits)
    with cols[1]:
        c.stat("Duty remitted", c.money(total_debited), f"{len(debits)} certificate(s)")
    with cols[2]:
        runway = int(balance // 100) if balance else 0
        c.stat("Runway", f"{runway}", "more ₹100 certificates", tone="danger" if runway < 100 else "")
    with cols[3]:
        with st.container(border=True):
            amount = st.number_input("Top-up amount (₹)", min_value=1000, value=25000, step=5000, key="topup_amt")
            b1, b2 = st.columns(2)
            if b1.button("Replenish", type="primary", use_container_width=True, key="topup_btn"):
                new_balance = stamping.top_up_balance(amount, admin_user="ADMIN_CONSOLE")
                st.success(f"Replenished. New balance {c.money(new_balance)}.")
                st.rerun()
            if b2.button("Simulate low", use_container_width=True, key="sim_low"):
                cfg = session.query(SysConfig).filter_by(id="GLOBAL_CONFIG").first()
                cfg.stockholding_prepaid_balance = 8500.0
                session.commit()
                st.rerun()


def _analytics(session) -> None:
    agreements = session.query(Agreement).all()
    payments = session.query(Payment).filter_by(status="Success").all()
    completed = [a for a in agreements if a.status == "Completed"]

    m = st.columns(5)
    with m[0]:
        c.stat("Agreements", str(len(agreements)), "all time")
    with m[1]:
        c.stat("Executed", str(len(completed)), f"{(100 * len(completed) / len(agreements)) if agreements else 0:.0f}% conversion", tone="ok")
    with m[2]:
        c.stat("Platform revenue", c.money(sum(p.platform_fee + p.gst_amount for p in payments)), "fees + GST")
    with m[3]:
        gmv = sum(a.get_commercial_terms().get("monthly_rent", 0) * a.get_commercial_terms().get("lease_months", 11) for a in completed)
        c.stat("Contract GMV", c.money(gmv), "value under lease")
    with m[4]:
        times = [(a.executed_at - a.created_at).total_seconds() / 60 for a in completed if a.executed_at and a.created_at]
        c.stat("Median execution", f"{sorted(times)[len(times) // 2]:.0f} min" if times else "—", "draft to seal")

    st.write("")
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Funnel — where users drop off**")
        reached = {
            "1 · Draft created": len(agreements),
            "2 · Paid & stamped": len([a for a in agreements if a.status in ("Paid", "Pending_Signatures", "Completed")]),
            "3 · Links dispatched": len([a for a in agreements if a.status in ("Pending_Signatures", "Completed")]),
            "4 · All signed & sealed": len(completed),
        }
        st.bar_chart(pd.DataFrame({"agreements": list(reached.values())}, index=list(reached)), color="#1E3A8A")
        st.caption("Biggest drop is the step to fix first.")
    with right:
        st.markdown("**Revenue by state and stamp denomination**")
        if payments:
            by_state = Counter()
            for p in payments:
                agr = next((a for a in agreements if a.id == p.agreement_id), None)
                by_state[agr.state_code if agr else "—"] += p.total_amount
            st.bar_chart(pd.DataFrame({"₹ collected": dict(by_state)}), color="#059669")
            denoms = Counter(f"₹{int(p.stamp_duty_amount)}" for p in payments)
            st.caption("Stamp denominations: " + ", ".join(f"{k} × {v}" for k, v in denoms.most_common()))
        else:
            c.empty_state("📊", "No transactions yet", "Charts populate as agreements are paid and executed.")


def _agent_console(session) -> None:
    agent = WorkflowAgent(session)
    st.markdown("**Autonomous workflow agent**")
    st.caption("Observes every active agreement and advances it: dispatch links after payment, remind daily, expire stale "
               "windows, seal on the last signature, purge unconsented drafts. It never pays, stamps or signs.")

    active = session.query(Agreement).filter(Agreement.status.in_(["Paid", "Pending_Signatures"])).all()
    cols = st.columns([1, 1, 2])
    with cols[0]:
        c.stat("Active agreements", str(len(active)), "in the agent's scope")
    with cols[1]:
        runs = session.query(AgentRun).count()
        c.stat("Agent runs", str(runs), "journaled")
    with cols[2]:
        if st.button("Run agent sweep now", type="primary", use_container_width=True):
            with st.spinner("Agent working…"):
                summary = agent.sweep(triggered_by="ADMIN_CONSOLE")
            st.session_state["last_sweep"] = summary
            st.rerun()
        sweep = st.session_state.get("last_sweep")
        if sweep:
            st.caption(f"Visited {sweep['agreements_visited']} agreement(s), purged {sweep['purged_drafts']} expired draft(s).")

    if active:
        st.write("")
        st.markdown("**Plans for active agreements**")
        for agr in active[:8]:
            with st.container(border=True):
                head = st.columns([2.4, 1, 1])
                head[0].markdown(f"**{c.esc(agr.display_title)}** {c.status_pill(agr.status)}", unsafe_allow_html=True)
                head[1].markdown(f"<span class='gl-mono'>{agr.signed_count()}/{len(agr.parties)} signed</span>", unsafe_allow_html=True)
                if head[2].button("Run for this", key=f"agent_{agr.id}", use_container_width=True):
                    run = agent.run(agr, triggered_by="ADMIN_CONSOLE")
                    st.toast(f"{run.status}: {run.outcome[:90]}")
                    st.rerun()
                for step in agent.plan(agr):
                    st.markdown(f"<span style='color:#64748B;font-size:.85rem'>→ {c.esc(step)}</span>", unsafe_allow_html=True)

    st.write("")
    st.markdown("**Recent agent runs**")
    runs = agent.recent_runs(limit=12)
    if not runs:
        c.empty_state("🤖", "No agent runs yet", "Run a sweep, or let the Copilot act, and every step is journaled here.")
    for r in runs:
        with st.expander(f"{r.agent_type} · {r.status} · {r.created_at.strftime('%d %b %H:%M') if r.created_at else ''} · {r.goal[:70]}"):
            st.markdown(f"{c.status_pill(r.status, r.status)} model `{c.esc(r.model)}` · "
                        f"{r.input_tokens + r.output_tokens} tokens", unsafe_allow_html=True)
            st.write(r.outcome or "")
            steps = r.get_steps()
            if steps:
                st.markdown("**Steps**")
                for s in steps:
                    st.markdown(f"<span class='gl-chat-action'>{'✔' if s.get('ok', True) else '✖'} {c.esc(s.get('tool'))} — "
                                f"{c.esc(str(s.get('output'))[:200])}</span>", unsafe_allow_html=True)


def _users_admin(session) -> None:
    users = session.query(User).order_by(User.created_at.desc()).all()
    st.markdown(f"**{len(users)} registered users**")
    search = st.text_input("Search by name, email or mobile", key="user_search")
    for u in users:
        if search and search.lower() not in f"{u.full_name} {u.email} {u.phone}".lower():
            continue
        with st.container(border=True):
            cols = st.columns([2.4, 1.4, 1, 1])
            cols[0].markdown(f"**{c.esc(u.full_name)}** {'· admin' if u.is_admin else ''}<br/>"
                             f"<span style='font-size:.82rem;color:#64748B'>{c.esc(u.email)} · {c.esc(u.phone)}</span>", unsafe_allow_html=True)
            initiated = session.query(Agreement).filter_by(initiator_id=u.id).count()
            cols[1].markdown(f"<span style='font-size:.85rem'>{initiated} agreement(s)<br/>"
                             f"joined {u.created_at.strftime('%d %b %Y') if u.created_at else '—'}</span>", unsafe_allow_html=True)
            suspicious = session.query(LoginEvent).filter_by(user_id=u.id, suspicious=True).count()
            cols[2].markdown(c.status_pill("Rejected", f"{suspicious} alerts") if suspicious else c.status_pill("Signed", "Clean"),
                             unsafe_allow_html=True)
            with cols[3]:
                if u.is_active:
                    if st.button("Suspend", key=f"susp_{u.id}", use_container_width=True):
                        u.is_active = False
                        session.commit()
                        st.rerun()
                else:
                    if st.button("Reactivate", key=f"react_{u.id}", use_container_width=True, type="primary"):
                        u.is_active = True
                        session.commit()
                        st.rerun()


def _templates_admin(session) -> None:
    st.markdown("**Clause library**")
    st.caption("Statutory clauses are locked by the compliance engine. Optional covenants are exposed to users as toggles.")
    for cl in get_default_clauses():
        lock = "🔒 statutory" if not cl["derogable"] else "adjustable"
        with st.expander(f"{cl['title']} · {lock}"):
            st.write(cl["text"])
            st.caption(f"id `{cl['id']}`")
    st.write("")
    st.markdown("**Toggles offered in the wizard**")
    for key, spec in OPTIONAL_TOGGLES.items():
        st.markdown(f"- **{c.esc(spec['label'])}** (default {'on' if spec['default'] else 'off'})")
    st.write("")
    st.markdown("**State stamp rules**")
    st.dataframe(pd.DataFrame([{"State": v["name"], "Code": k, "Flat duty (₹)": v["flat_duty"],
                                "% of consideration": v.get("pct_rate", 0) * 100, "Article": v.get("article", "")}
                               for k, v in STATE_STAMP_RULES.items()]), use_container_width=True, hide_index=True)


def _feedback_console(session) -> None:
    rows = session.query(Feedback).order_by(Feedback.created_at.desc()).all()
    if not rows:
        c.empty_state("⭐", "No feedback yet", "NPS responses from the workspace land here with detractor root causes.")
        return
    promoters = len([f for f in rows if f.score >= 9])
    detractors = len([f for f in rows if f.score <= 6])
    passives = len(rows) - promoters - detractors
    nps = round(100 * (promoters - detractors) / len(rows))
    m = st.columns(4)
    with m[0]:
        c.stat("NPS", str(nps), "target > 60", tone="ok" if nps >= 60 else "danger" if nps < 0 else "")
    with m[1]:
        c.stat("Promoters", str(promoters), "9 and 10")
    with m[2]:
        c.stat("Passives", str(passives), "7 and 8")
    with m[3]:
        c.stat("Detractors", str(detractors), "0 to 6", tone="danger" if detractors else "")
    st.write("")
    causes = Counter(f.category for f in rows if f.category)
    if causes:
        st.markdown("**Detractor root causes**")
        st.bar_chart(pd.DataFrame({"responses": dict(causes)}), color="#B91C1C")
    for f in rows[:20]:
        with st.container(border=True):
            st.markdown(f"{c.status_pill('Completed' if f.score >= 9 else 'Expired' if f.score <= 6 else 'Pending', f'{f.score}/10')} "
                        f"<b>{c.esc(f.category or f.sentiment)}</b> · <span style='font-size:.8rem;color:#64748B'>"
                        f"{f.created_at.strftime('%d %b %Y') if f.created_at else ''}</span>", unsafe_allow_html=True)
            if f.comment:
                st.write(f.comment)


def _audit_console(session) -> None:
    tab1, tab2, tab3 = st.tabs(["Agreement audit trail", "Stamping journal", "Notifications"])
    with tab1:
        logs = session.query(AuditLog).order_by(AuditLog.recorded_at.desc()).limit(60).all()
        if not logs:
            c.empty_state("📜", "No events yet", "Every payment, stamping, signature and seal is journaled append-only.")
        else:
            st.dataframe(pd.DataFrame([{
                "Recorded (UTC)": l.recorded_at.strftime("%d %b %H:%M:%S") if l.recorded_at else "",
                "Agreement": l.agreement_id[:8], "Event": l.event_type, "Actor": l.triggered_by,
                "Payload": (l.event_data or "")[:120]} for l in logs]), use_container_width=True, hide_index=True, height=420)
    with tab2:
        journals = session.query(SysConfigJn).order_by(SysConfigJn.timestamp.desc()).limit(40).all()
        st.dataframe(pd.DataFrame([{
            "Timestamp (UTC)": j.timestamp.strftime("%d %b %H:%M:%S") if j.timestamp else "",
            "Operation": j.operation, "Actor": j.updated_by_user,
            "Previous": (j.previous_value or "")[:60], "New": (j.new_value or "")[:100]} for j in journals]),
            use_container_width=True, hide_index=True, height=380)
        st.caption("`sysconfigTlb$jn` is append-only: every debit and top-up is reconcilable against SHCIL statements.")
    with tab3:
        notes = session.query(Notification).order_by(Notification.created_at.desc()).limit(40).all()
        if not notes:
            c.empty_state("📨", "No dispatches yet", "Signing invitations, reminders and completion notices are logged here.")
        else:
            st.dataframe(pd.DataFrame([{
                "Sent (UTC)": n.created_at.strftime("%d %b %H:%M") if n.created_at else "", "Kind": n.kind,
                "Channel": n.channel, "Recipient": n.recipient, "By": n.triggered_by,
                "Message": (n.message or "")[:90]} for n in notes]), use_container_width=True, hide_index=True, height=380)


def render_admin(session, user) -> None:
    if not user or not user.is_admin:
        st.markdown("### Operations console")
        c.notice("This console is restricted to platform administrators. Sign in with the operations persona to explore it.", "warn")
        return

    stamping = StampingService(session)
    st.markdown("### Operations console")
    st.caption("Treasury, analytics, the autonomous agent, users, templates, feedback and the evidentiary journal.")
    _treasury(session, stamping)
    st.write("")
    tabs = st.tabs(["Analytics", "Workflow agent", "Users", "Templates & rules", "Feedback & NPS", "Audit journal"])
    with tabs[0]:
        _analytics(session)
    with tabs[1]:
        _agent_console(session)
    with tabs[2]:
        _users_admin(session)
    with tabs[3]:
        _templates_admin(session)
    with tabs[4]:
        _feedback_console(session)
    with tabs[5]:
        _audit_console(session)
