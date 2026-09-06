"""
Tests for the AI / agent layer: ingestion, clause intelligence, benchmarks, tool guardrails,
Copilot rule router, LLM loop (with a fake model) and the autonomous Workflow Agent (TC-AI)
"""
from datetime import timedelta

import pytest

from ai.clause_intelligence import ClauseIntelligence, redact_pii
from ai.contract_ingest import extract_terms, extract_terms_rule_based, merge_into_payload
from ai.copilot import Copilot
from ai.llm import LLMClient, LLMResponse, LLMUnavailableError, NullLLMClient, ToolCall, extract_json
from ai.rent_benchmark import benchmark, supported_cities
from ai.tools import ToolContext, build_registry
from ai.workflow_agent import WorkflowAgent
from domain.models import AgentRun, Notification, utc_now
from services.agreement_service import AgreementService, demo_payload, empty_payload
from services.esign_service import ESignService
from services.stamping_service import StampingService
from services.workflow_service import WorkflowService

BRIEF = ("Rent agreement for Flat 402 Sunrise Apartments, Bellandur, Bangalore 560103. Rent 28,000 per month, "
         "deposit 1.2 lakh, 11 months, lock-in 6 months, notice 30 days, 5% escalation from 2026-10-01. "
         "Owner Ramakiran Reddy 9876543210 ramakiran@example.com PAN ABCDE1234F, tenant Mayank Tripathi 9876543211 "
         "mayank@example.com. Witness Suresh Kumar 9876543212")


class TestContractIngest:
    def test_rule_based_extraction(self):
        r = extract_terms_rule_based(BRIEF)
        u = r.payload_updates
        assert u["commercials"]["monthly_rent"] == 28000
        assert u["commercials"]["security_deposit"] == 120000
        assert u["commercials"]["lease_months"] == 11
        assert u["commercials"]["lock_in_months"] == 6
        assert u["commercials"]["notice_days"] == 30
        assert u["commercials"]["escalation_pct"] == 5.0
        assert u["commercials"]["lease_start"] == "2026-10-01"
        assert u["property"]["pincode"] == "560103" and u["property"]["city"] == "Bangalore"
        assert u["state_code"] == "KA"
        assert u["owners"][0] == {"name": "Ramakiran Reddy", "email": "ramakiran@example.com", "phone": "9876543210", "pan": "ABCDE1234F"}
        assert u["tenants"][0]["name"] == "Mayank Tripathi"
        assert u["witnesses"][0]["phone"] == "9876543212"
        assert r.confidence >= 0.9

    @pytest.mark.parametrize("text,premises,address,city", [
        ("Draft: 2BHK at Sunrise Apartments 402, Bellandur, Bangalore 560103. Rent 28000, deposit 120000",
         "Sunrise Apartments, 402", "Bellandur", "Bangalore"),
        ("Rent agreement for Flat 402 Sunrise Apartments, Bellandur, Bangalore 560103. Rent 28000",
         "Flat 402", "Bellandur", "Bangalore"),
        ("I want to rent my 3BHK villa in Whitefield, Bangalore 560066 for 55000 a month",
         "", "Whitefield", "Bangalore"),
        ("Lease of house no 12, Dwarka Sector 10, New Delhi 110075, rent 30000",
         "House 12", "Dwarka Sector 10", "Delhi"),
        ("Renting out Flat B-204, Prestige Towers, Koramangala 4th Block, Bangalore 560034. Rent 45000",
         "Flat B-204", "Prestige Towers, Koramangala 4th Block", "Bangalore"),
    ])
    def test_address_extraction_across_phrasings(self, text, premises, address, city):
        prop = extract_terms_rule_based(text).payload_updates.get("property", {})
        assert prop.get("premises_name", "") == premises
        assert prop.get("address", "") == address
        assert prop.get("city") == city

    def test_empty_and_noise(self):
        assert extract_terms_rule_based("").fields_found == []
        r = extract_terms_rule_based("hello there")
        assert r.fields_found == [] and r.notes

    def test_merge_into_payload(self):
        merged = merge_into_payload(empty_payload(), extract_terms_rule_based(BRIEF).payload_updates)
        assert merged["owners"][0]["aadhaar"] == ""  # template keys preserved
        assert merged["commercials"]["rent_due_day"] == 5  # untouched defaults survive
        assert merged["property"]["city"] == "Bangalore"

    def test_extract_terms_without_model_falls_back(self):
        r = extract_terms(BRIEF)
        assert r.model == "rule-based"


class TestClauseIntelligence:
    def test_redact_pii(self):
        clean, n = redact_pii("Aadhaar 1234 5678 9012, PAN ABCDE1234F, call 9876543210")
        assert n == 3
        assert "1234 5678 9012" not in clean and "XXXXXXXX9012" in clean
        assert "ABCDE1234F" not in clean and "9876543210" not in clean

    def test_risk_scoring_flags_harsh_terms(self):
        ci = ClauseIntelligence(NullLLMClient())
        report = ci.assess_risk(
            "Deposit will be forfeited entirely if the tenant leaves early. Owner may enter the flat at any time. Tenant must vacate immediately on demand.",
            {"monthly_rent": 28000, "security_deposit": 400000, "lease_months": 11, "lock_in_months": 12, "notice_days": 7, "escalation_pct": 25},
        )
        ids = {f.id for f in report.findings}
        assert {"FORFEIT_DEPOSIT", "ENTRY_WITHOUT_NOTICE", "WAIVER_OF_NOTICE", "DEPOSIT_EXCESSIVE", "LOCKIN_GT_LEASE",
                "NOTICE_SHORT", "ESCALATION_HIGH"} <= ids
        assert report.level == "high" and report.score >= 40
        assert report.model == "rule-based"

    def test_risk_scoring_clean_terms(self):
        report = ClauseIntelligence(NullLLMClient()).assess_risk("Quiet hours after 11 PM.", demo_payload()["commercials"], state_code="KA")
        assert report.findings == [] and report.level == "low"

    def test_pii_in_clause_is_masked_and_flagged(self):
        report = ClauseIntelligence(NullLLMClient()).assess_risk("Tenant Aadhaar 1234-5678-9012 on file.", demo_payload()["commercials"])
        assert report.pii_redactions == 1
        assert "XXXXXXXX9012" in report.redacted_text
        assert any(f.id == "PII_IN_CLAUSE" for f in report.findings)

    def test_summary_and_vernacular_fallback(self):
        ci = ClauseIntelligence(NullLLMClient())
        s = ci.plain_language_summary(demo_payload())
        assert "Ramakiran Reddy" in s["summary"] and "28,000" in s["summary"]
        hi = ci.plain_language_summary(demo_payload(), language="hi")
        assert hi["language"] == "en" and "note" in hi

    def test_explain_clause_glossary(self):
        ci = ClauseIntelligence(NullLLMClient())
        assert "Section 65B" in ci.explain_clause("what is section 65b?")
        assert "lock-in" in ci.explain_clause("explain lock-in").lower()
        assert "I can explain" in ci.explain_clause("zzz unknown")


class TestRentBenchmark:
    def test_benchmark_positions(self):
        fair = benchmark("Bengaluru", "Bellandur", "2BHK", 30000, 180000)
        assert fair["supported"] and fair["locality"] == "Bellandur" and fair["rent_position"] == "fair"
        assert fair["deposit_position"] == "normal"
        high = benchmark("Delhi", "Dwarka", "2BHK", 60000, 300000)
        assert high["rent_position"] == "above_market" and high["deposit_position"] == "high"
        low = benchmark("Mumbai", "", "1BHK", 10000)
        assert low["rent_position"] == "below_market" and low["locality"] == "City average"
        assert not benchmark("Timbuktu")["supported"]
        assert "Bangalore" in supported_cities()


class TestToolRegistry:
    def test_human_tier_and_readonly_guardrails(self, db_session, sample_users):
        ctx = ToolContext(session=db_session, user=sample_users["owner"], payload=demo_payload(), mode="readonly")
        reg = build_registry(ctx)
        out, ok = reg.execute("pay_and_procure_estamp", {})
        assert not ok and "human-only" in out
        out, ok = reg.execute("prefill_agreement", {"title": "x"})
        assert not ok and "read-only" in out
        out, ok = reg.execute("nope", {})
        assert not ok
        out, ok = reg.execute("calculate_stamp_duty", {"state_code": "MH", "monthly_rent": 40000, "security_deposit": 200000})
        assert ok and '"state_code": "MH"' in out
        assert len(reg.calls) == 4
        assert "pay_and_procure_estamp" not in [d["name"] for d in reg.definitions(include_human=False)]

    def test_prefill_strips_aadhaar_and_validates(self, db_session, sample_users):
        ctx = ToolContext(session=db_session, user=sample_users["owner"], payload=empty_payload())
        reg = build_registry(ctx)
        out, ok = reg.execute("prefill_agreement", {"owners": [{"name": "Ramakiran Reddy", "phone": "9876543210", "email": "r@example.com",
                                                                 "pan": "ABCDE1234F", "aadhaar": "123456789012"}],
                                                    "commercials": {"monthly_rent": 28000}})
        assert ok and ctx.payload_changed
        assert ctx.payload["owners"][0].get("aadhaar", "") == ""
        assert ctx.payload["commercials"]["monthly_rent"] == 28000
        assert '"ready_for_payment": false' in out

    def test_save_draft_and_progress_tools(self, db_session, sample_users):
        ctx = ToolContext(session=db_session, user=sample_users["owner"], payload=demo_payload())
        reg = build_registry(ctx)
        out, ok = reg.execute("save_draft", {})
        assert ok and ctx.agreement_id
        out, ok = reg.execute("list_my_agreements", {})
        assert ok and ctx.agreement_id in out
        out, ok = reg.execute("get_signing_progress", {"agreement_id": ctx.agreement_id})
        assert ok and '"total_parties": 3' in out
        # a stranger cannot read it
        ctx2 = ToolContext(session=db_session, user=sample_users["tenant"], payload=demo_payload())
        out, ok = build_registry(ctx2).execute("send_signing_reminders", {"agreement_id": ctx.agreement_id})
        assert "reminders only apply" in out  # Draft: nothing to remind, and the tenant is not the initiator anyway


class TestCopilotRuleRouter:
    def _copilot(self, db_session, user, payload=None):
        ctx = ToolContext(session=db_session, user=user, payload=payload or demo_payload())
        return Copilot(ctx, llm=NullLLMClient())

    def test_pricing_intent(self, db_session, sample_users):
        reply = self._copilot(db_session, sample_users["owner"]).chat([], "How much is stamp duty in Maharashtra for rent 40,000 and deposit 2 lakh?")
        assert "Maharashtra" in reply.text and "0.25%" in reply.text and "₹" in reply.text
        assert reply.actions[0]["tool"] == "calculate_stamp_duty"
        assert reply.actions[0]["input"]["state_code"] == "MH"
        assert db_session.query(AgentRun).filter_by(agent_type="COPILOT").one().status == "COMPLETED"

    def test_draft_from_brief_intent_updates_payload(self, db_session, sample_users):
        cp = self._copilot(db_session, sample_users["owner"], empty_payload())
        reply = cp.chat([], "Draft: " + BRIEF)
        assert reply.payload_changed
        assert reply.payload["commercials"]["monthly_rent"] == 28000
        assert reply.payload["owners"][0]["name"] == "Ramakiran Reddy"
        assert "filled the draft" in reply.text
        assert "Still needed" in reply.text  # tenant PAN etc. not required, but Aadhaar/email present -> witnesses email missing

    def test_risk_summary_and_explain_intents(self, db_session, sample_users):
        payload = demo_payload()
        payload["custom_clauses"] = "Deposit is non-refundable if tenant leaves early."
        cp = self._copilot(db_session, sample_users["owner"], payload)
        risk = cp.chat([], "Review my clauses for risk")
        assert "Deposit forfeiture" in risk.text
        summary = cp.chat([], "Summarise the agreement in simple words")
        assert "Ramakiran Reddy" in summary.text
        hindi = cp.chat([], "Explain this agreement in Hindi")
        assert "Vernacular" in hindi.text or "AI service" in hindi.text
        explain = cp.chat([], "What is an e-stamp?")
        assert "Stock Holding" in explain.text

    def test_status_and_reminder_intents(self, db_session, sample_users):
        owner = sample_users["owner"]
        agreements = AgreementService(db_session)
        wf = WorkflowService(db_session)
        agr = agreements.save_draft(owner, demo_payload())
        wf.transition_state(agr, "Paid")
        wf.open_for_signatures(agr)
        cp = self._copilot(db_session, owner)
        status = cp.chat([], "Who has signed? Show status")
        assert "Signing matrix" in status.text and "Pending" in status.text or "Sent" in status.text
        remind = cp.chat([], "Please remind everyone who hasn't signed")
        assert "Done" in remind.text
        assert db_session.query(Notification).filter_by(agreement_id=agr.id, kind="REMINDER").count() == 3

    def test_help_and_benchmark_intents(self, db_session, sample_users):
        cp = self._copilot(db_session, sample_users["tenant"])
        assert "Copilot" in cp.chat([], "hello").text
        fair = cp.chat([], "Is rent 30000 fair for a 2BHK in Bellandur, Bangalore?")
        assert "Bellandur" in fair.text and "typical rent" in fair.text


class FakeLLM(LLMClient):
    """Scripted model: first asks for a tool, then answers using the result."""
    available = True
    model = "fake-claude"

    def __init__(self):
        self.calls = 0

    def complete(self, system, messages, tools=None, max_tokens=None):
        self.calls += 1
        if self.calls == 1:
            assert tools and any(t["name"] == "calculate_stamp_duty" for t in tools)
            return LLMResponse(text="", tool_calls=[ToolCall(id="tu_1", name="calculate_stamp_duty", input={"state_code": "KA"})],
                               stop_reason="tool_use", input_tokens=120, output_tokens=30,
                               raw_content=[{"type": "tool_use", "id": "tu_1", "name": "calculate_stamp_duty", "input": {"state_code": "KA"}}])
        last = messages[-1]["content"]
        assert last[0]["type"] == "tool_result" and last[0]["tool_use_id"] == "tu_1"
        return LLMResponse(text="Karnataka stamp duty is ₹100; total ₹452.82.", stop_reason="end_turn", input_tokens=200, output_tokens=40)


class TestCopilotLLMLoop:
    def test_tool_loop_with_fake_model(self, db_session, sample_users):
        ctx = ToolContext(session=db_session, user=sample_users["owner"], payload=demo_payload())
        cp = Copilot(ctx, llm=FakeLLM())
        reply = cp.chat([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}], "What does it cost in Karnataka?")
        assert reply.mode == "fake-claude"
        assert "₹100" in reply.text
        assert reply.actions[0]["tool"] == "calculate_stamp_duty" and reply.actions[0]["ok"]
        run = db_session.query(AgentRun).one()
        assert run.model == "fake-claude" and run.input_tokens == 320 and run.get_steps()[0]["tool"] == "calculate_stamp_duty"

    def test_unavailable_model_degrades_gracefully(self, db_session, sample_users):
        class Flaky(LLMClient):
            available = True
            model = "flaky"

            def complete(self, *a, **k):
                raise LLMUnavailableError("rate limited")

        ctx = ToolContext(session=db_session, user=sample_users["owner"], payload=demo_payload())
        reply = Copilot(ctx, llm=Flaky()).chat([], "How much is stamp duty in Delhi?")
        assert "Delhi" in reply.text and "rate limited" in reply.text

    def test_extract_json_helper(self):
        assert extract_json('Here you go:\n```json\n{"a": 1}\n```') == {"a": 1}
        assert extract_json('prefix [{"x": 2}] suffix') == [{"x": 2}]
        assert extract_json("no json here") is None


class TestWorkflowAgent:
    def _paid_agreement(self, db_session, owner):
        agreements = AgreementService(db_session)
        agr = agreements.save_draft(owner, demo_payload())
        StampingService(db_session).procure_estamp(agr.id, "KA", 100.0, owner.full_name)
        WorkflowService(db_session).transition_state(agr, "Paid")
        return agr

    def test_plan_and_run_across_lifecycle(self, db_session, sample_users):
        owner = sample_users["owner"]
        agent = WorkflowAgent(db_session)
        agreements = AgreementService(db_session)

        draft = agreements.save_draft(owner, demo_payload())
        assert "human gate" in agent.plan(draft)[1]
        run = agent.run(draft)
        assert run.status == "NEEDS_HUMAN" and run.get_steps()[1]["output"]["gate"] == "PAYMENT"

        agr = self._paid_agreement(db_session, owner)
        assert "Dispatch signing invitations" in agent.plan(agr)[1]
        run = agent.run(agr)
        assert run.status == "COMPLETED" and agr.status == "Pending_Signatures"
        assert run.get_steps()[0]["output"]["detail"] == "Dispatched 3 signing link(s)"

        # Nothing due yet -> wait
        run = agent.run(agr)
        assert run.get_steps()[0]["tool"] == "wait"

        # A day later -> reminders
        later = utc_now() + timedelta(hours=21)
        run = agent.run(agr, now=later)
        assert run.get_steps()[0]["tool"] == "remind" and len(run.get_steps()[0]["output"]["recipients"]) == 3

        # Everyone signs -> agent seals
        esign = ESignService(db_session)
        for p in agr.parties:
            esign.verify_otp_and_sign(agr.id, p.id, p.aadhaar_masked, "123456", True)
        run = agent.run(agr)
        assert run.get_steps()[0]["tool"] == "seal" and agr.status == "Completed" and agr.final_pdf_sha256

        # Completed -> verify digest
        run = agent.run(agr)
        assert run.get_steps()[0]["tool"] == "verify_seal" and run.get_steps()[0]["ok"]

    def test_agent_expires_breached_window_and_sweeps(self, db_session, sample_users):
        owner = sample_users["owner"]
        agent = WorkflowAgent(db_session)
        agr = self._paid_agreement(db_session, owner)
        agent.run(agr)
        agr.expires_at = utc_now() - timedelta(minutes=1)
        db_session.commit()
        summary = agent.sweep()
        assert summary["agreements_visited"] == 1
        assert agr.status == "Expired"
        assert any(r["outcome"].startswith("Signing window breached") for r in summary["runs"])
        assert len(agent.recent_runs()) >= 2

    def test_agent_never_bypasses_payment_gate(self, db_session, sample_users):
        agreements = AgreementService(db_session)
        agr = agreements.save_draft(sample_users["owner"], demo_payload())
        WorkflowService(db_session).transition_state(agr, "Paid")  # paid but no e-stamp certificate
        run = WorkflowAgent(db_session).run(agr)
        assert run.status == "NEEDS_HUMAN" and agr.status == "Paid"
