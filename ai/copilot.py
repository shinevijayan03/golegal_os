"""
GoLegal Copilot - conversational contracting assistant.

With a model configured it runs a tool-using agent loop over the ToolRegistry.
Without one it routes intents deterministically to the same tools, so the
assistant is always useful (and testable) offline. Every run is journaled as an
AgentRun with its tool calls.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai.llm import LLMClient, LLMUnavailableError, get_llm_client
from ai.tools import ToolContext, ToolRegistry, build_registry
from config import settings
from domain.models import AgentRun, utc_now
from services.rule_engine import STATE_STAMP_RULES

SYSTEM_PROMPT = """You are GoLegal Copilot, the in-product assistant of GoLegal - an Indian platform for drafting, e-stamping and Aadhaar e-signing rental agreements in under ten minutes.

How you work
- You help tenants, owners and witnesses draft, understand, price and track agreements. Use the tools for anything factual: prices always come from calculate_stamp_duty, rent norms from get_rent_benchmark, clause safety from assess_clause_risk.
- When the user describes an agreement in plain words, call extract_terms_from_text (or prefill_agreement for specific fields) so the draft fills itself, then tell them what is still missing (get_draft_status).
- Payment, e-Stamp purchase and Aadhaar eSign are personal legal acts: you never perform them. Explain where in the app the user does them (Checkout step, then each party's secure link).
- Never ask for or repeat a full Aadhaar number. Masked form (XXXXXXXX1234) is the only acceptable form.
- Be concrete and brief. Use rupee amounts with the ₹ symbol. No legal disclaimers unless the user asks about enforceability; then explain the IT Act 2000 and Section 65B basis in one or two sentences.
- If a question is outside residential/commercial contracting in India, say so and point to what you can help with.

Statutory context: 11-month residential rentals need e-stamp paper (Karnataka/Delhi ₹100 flat; Maharashtra 0.25% leave-and-licence) and are valid without registration; 12 months or more need Sub-Registrar registration. Aadhaar eSign is recognised under Sections 4, 5 and 10A of the IT Act 2000; GoLegal appends a Section 65B certificate to every sealed deed. Witnesses attest but do not receive a copy of the executed deed.
"""

STATE_WORDS = {v["name"].lower(): k for k, v in STATE_STAMP_RULES.items()}
STATE_WORDS.update({"bangalore": "KA", "bengaluru": "KA", "karnataka": "KA", "delhi": "DL", "mumbai": "MH", "pune": "MH",
                    "maharashtra": "MH", "chennai": "TN", "hyderabad": "TS", "gurgaon": "HR", "gurugram": "HR", "noida": "UP"})


@dataclass
class CopilotReply:
    text: str
    actions: List[Dict[str, Any]] = field(default_factory=list)
    payload: Optional[Dict[str, Any]] = None
    payload_changed: bool = False
    mode: str = "rule-based"
    run_id: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)


class Copilot:
    def __init__(self, ctx: ToolContext, llm: Optional[LLMClient] = None):
        self.ctx = ctx
        self.llm = llm or ctx.llm or get_llm_client()
        self.ctx.llm = self.llm
        self.registry: ToolRegistry = build_registry(ctx)

    # ------------------------------------------------------------------ public
    def chat(self, history: List[Dict[str, str]], user_message: str) -> CopilotReply:
        user_message = (user_message or "").strip()
        if not user_message:
            return CopilotReply(text="Tell me about the agreement you need, or ask about stamp duty, clauses or signing.")
        run = AgentRun(agent_type="COPILOT", user_id=self.ctx.user.id if self.ctx.user else None,
                       agreement_id=self.ctx.agreement_id, goal=user_message[:2000], status="RUNNING",
                       model=self.llm.model if self.llm.available else "rule-based")
        self.ctx.session.add(run)
        self.ctx.session.flush()
        try:
            if self.llm.available:
                try:
                    reply = self._chat_llm(history, user_message, run)
                except LLMUnavailableError as exc:
                    reply = self._chat_rules(user_message)
                    reply.text = f"{reply.text}\n\n_(AI service unavailable: {exc}. Answered with built-in rules.)_"
            else:
                reply = self._chat_rules(user_message)
            reply.actions = list(self.registry.calls)
            reply.payload = self.ctx.payload
            reply.payload_changed = self.ctx.payload_changed
            run.status = "COMPLETED"
            run.outcome = reply.text[:4000]
            run.set_steps(self.registry.calls)
            run.completed_at = utc_now()
            reply.run_id = run.id
            self.ctx.session.commit()
            return reply
        except Exception as exc:
            run.status = "FAILED"
            run.outcome = f"{type(exc).__name__}: {exc}"
            run.completed_at = utc_now()
            self.ctx.session.commit()
            raise

    # ------------------------------------------------------------------ LLM loop
    def _context_block(self) -> str:
        p = self.ctx.payload
        user = self.ctx.user
        snapshot = {
            "signed_in_user": {"name": user.full_name, "email": user.email, "is_admin": user.is_admin} if user else None,
            "active_agreement_id": self.ctx.agreement_id,
            "draft": {
                "agreement_type": p.get("agreement_type"), "state_code": p.get("state_code"),
                "owners": [{k: o.get(k) for k in ("name", "phone", "email")} for o in p.get("owners", [])],
                "tenants": [{k: t.get(k) for k in ("name", "phone", "email")} for t in p.get("tenants", [])],
                "witnesses": [{k: w.get(k) for k in ("name", "phone")} for w in p.get("witnesses", [])],
                "property": p.get("property"), "commercials": p.get("commercials"),
                "clause_toggles": p.get("clause_toggles"), "custom_clauses": (p.get("custom_clauses") or "")[:500],
            },
        }
        return "Current app context (JSON):\n" + json.dumps(snapshot, default=str)

    def _chat_llm(self, history: List[Dict[str, str]], user_message: str, run: AgentRun) -> CopilotReply:
        messages: List[Dict[str, Any]] = [{"role": m["role"], "content": m["content"]} for m in history[-12:]
                                          if m.get("role") in ("user", "assistant") and m.get("content")]
        messages.append({"role": "user", "content": f"{self._context_block()}\n\nUser: {user_message}"})
        tools = self.registry.definitions(include_human=False)
        total_in = total_out = 0
        final_text = ""
        for _ in range(settings.agent_max_tool_calls):
            resp = self.llm.complete(SYSTEM_PROMPT, messages, tools=tools)
            total_in += resp.input_tokens
            total_out += resp.output_tokens
            if resp.stop_reason == "refusal":
                final_text = "I can't help with that request. I can help you draft, price, review or track a rental agreement."
                break
            if not resp.wants_tools:
                final_text = resp.text
                break
            messages.append({"role": "assistant", "content": resp.raw_content})
            results = []
            for call in resp.tool_calls:
                out, ok = self.registry.execute(call.name, call.input)
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": out, "is_error": not ok})
            messages.append({"role": "user", "content": results})
        else:
            final_text = final_text or "I ran out of steps before finishing. Here is what I found so far: " + \
                "; ".join(f"{c['tool']} -> {'ok' if c['ok'] else 'failed'}" for c in self.registry.calls)
        run.input_tokens, run.output_tokens = total_in, total_out
        return CopilotReply(text=final_text or "Done.", mode=self.llm.model)

    # ------------------------------------------------------------------ rule-based router
    def _run(self, name: str, **inp) -> Dict[str, Any]:
        out, ok = self.registry.execute(name, inp)
        try:
            return json.loads(out)
        except ValueError:
            return {"error": out}

    def _chat_rules(self, msg: str) -> CopilotReply:
        low = msg.lower()
        state = next((code for word, code in STATE_WORDS.items() if re.search(r"\b" + re.escape(word) + r"\b", low)), None)

        # Greetings / help
        if re.fullmatch(r"\s*(hi|hello|hey|help|what can you do|namaste)[!. ]*\s*", low):
            return CopilotReply(text=self._help_text(), suggestions=self._default_suggestions())

        # Signing progress / status
        if re.search(r"\b(status|progress|who (has )?signed|pending|signed yet|track)\b", low) and not re.search(r"\b(remind|resend)\b", low):
            if not self.ctx.user:
                return CopilotReply(text="Sign in and I will show who has signed and who is pending on each agreement.")
            data = self._run("list_my_agreements")
            rows = data.get("agreements", [])
            if not rows:
                return CopilotReply(text="You have no agreements yet. Describe one and I will draft it - for example: "
                                         "'2BHK in Bellandur, rent 28k, deposit 1.2 lakh, owner Ramakiran Reddy, tenant Mayank Tripathi'.")
            pending = [r for r in rows if r["status"] == "Pending_Signatures"]
            lines = [f"You have {len(rows)} agreement(s): " + ", ".join(f"{r['title']} ({r['status'].replace('_', ' ').lower()}, {r['signed']} signed)" for r in rows[:6]) + "."]
            if len(pending) == 1:
                prog = self._run("get_signing_progress", agreement_id=pending[0]["id"])
                lines.append("Signing matrix for " + prog.get("title", "the pending agreement") + ": " +
                             "; ".join(f"{p['name']} ({p['type']}) - {p['status']}" for p in prog.get("parties", [])) + ".")
                if prog.get("expires_at"):
                    lines.append(f"Signing window closes {prog['expires_at'][:10]}.")
            return CopilotReply(text="\n\n".join(lines), suggestions=["Send reminders to pending parties", "Explain Section 65B"])

        # Reminders
        if re.search(r"\b(remind|resend|nudge|chase|follow ?up)\b", low):
            if not self.ctx.user:
                return CopilotReply(text="Sign in first, then I can re-send signing links to anyone who has not signed.")
            data = self._run("send_signing_reminders")
            if "error" in data:
                return CopilotReply(text=f"I could not send reminders: {data['error']}")
            if data.get("sent"):
                return CopilotReply(text=f"Done. Fresh signing links went out to {', '.join(data['recipients'])} via WhatsApp, SMS and email.")
            return CopilotReply(text=data.get("note") or "Everyone has already signed - nothing to remind.")

        # Definitions come before pricing so "what is an e-stamp?" is explained, not priced
        is_definition = re.match(r"\s*(what is|what's|whats|what does|explain|define|meaning of|why do i need|is it (legal|valid))", low)
        asks_summary = re.search(r"\b(hindi|kannada|tamil|telugu|summar|simple words|plain (english|language))\b", low) or \
            re.search(r"\b(this|the|my) (agreement|draft|deed)\b", low)
        asks_price = re.search(r"\b(cost|price|fee|how much|total)\b", low)
        if is_definition and not asks_summary and not asks_price:
            e = self._run("explain_legal_term", term=msg)
            return CopilotReply(text=e.get("explanation", ""), suggestions=["What will stamp duty cost?", "Draft my agreement"])

        # Stamp duty / pricing
        if re.search(r"\b(stamp duty|stamp|duty|cost|price|fee|charges?|how much|total payable|gst)\b", low):
            nums = self._numbers(low)
            inp: Dict[str, Any] = {}
            if state:
                inp["state_code"] = state
            if nums.get("rent"):
                inp["monthly_rent"] = nums["rent"]
            if nums.get("deposit"):
                inp["security_deposit"] = nums["deposit"]
            q = self._run("calculate_stamp_duty", **inp)
            text = (f"For {q['state_name']} ({q['article']}): stamp duty ₹{q['stamp_duty_amount']:,.2f}, GoLegal fee ₹{q['platform_fee']:,.2f}, "
                    f"GST ₹{q['gst_amount']:,.2f} - total ₹{q['total_payable']:,.2f}.")
            if q["state_code"] == "MH":
                text += " Maharashtra duty is 0.25% of the total consideration (rent for the term plus 10% notional interest on the deposit), minimum ₹500."
            else:
                text += " The duty is a flat statutory amount for 11-month rentals; the platform fee covers drafting, e-stamp procurement, multi-party eSign and sealing."
            return CopilotReply(text=text, suggestions=["Is my rent fair for this locality?", "Review my clauses for risk"])

        # Fair rent
        if re.search(r"\b(fair|market|benchmark|too (high|much|low)|going rate|reasonable rent|deposit (norm|normal|too))\b", low):
            nums = self._numbers(low)
            inp = {}
            city = next((w for w in ("bangalore", "bengaluru", "delhi", "mumbai", "hyderabad", "chennai", "pune", "gurgaon", "gurugram") if w in low), None)
            if city:
                inp["city"] = city
            m = re.search(r"\b([1-4])\s*-?\s*bhk\b", low)
            if m:
                inp["bhk"] = f"{m.group(1)}BHK"
            loc = re.search(r"\bin\s+([a-z][a-z ]{2,25}?)(?:[,.]|\s+(?:for|at|rent|with)|$)", low)
            if loc and loc.group(1).strip() not in ("bangalore", "delhi", "mumbai"):
                inp["locality"] = loc.group(1).strip()
            if nums.get("rent"):
                inp["monthly_rent"] = nums["rent"]
            if nums.get("deposit"):
                inp["security_deposit"] = nums["deposit"]
            b = self._run("get_rent_benchmark", **inp)
            if not b.get("supported"):
                return CopilotReply(text=b.get("message", "No benchmark available."))
            text = (f"{b['bhk']} in {b['locality']}, {b['city']}: typical rent ₹{b['fair_rent_low']:,}–₹{b['fair_rent_high']:,} per month; "
                    f"deposits run {b['deposit_norm_months'][0]}–{b['deposit_norm_months'][1]} months. " + " ".join(b.get("insights", [])))
            return CopilotReply(text=text, suggestions=["What will stamp duty cost?", "Draft the agreement with these terms"])

        # Risk review
        if re.search(r"\b(risk|review|fair clause|unfair|enforceable|check (my|the) (clause|terms|draft)|is this ok|red flag)\b", low):
            r = self._run("assess_clause_risk")
            if not r.get("findings"):
                return CopilotReply(text="I reviewed the draft: no risk signals. Deposit, lock-in, notice and escalation are within customary Indian norms and the custom covenants look fair.",
                                    suggestions=["Summarise the agreement in simple words", "What will it cost?"])
            lines = [f"Risk {r['level'].upper()} (score {r['score']}/100). {r['summary']}"]
            for f in r["findings"][:6]:
                lines.append(f"- [{f['severity']}] {f['title']}: {f['detail']} Suggestion: {f['suggestion']}")
            if r.get("pii_redactions"):
                lines.append(f"I masked {r['pii_redactions']} identity number(s) found in the clause text.")
            return CopilotReply(text="\n".join(lines), suggestions=["Fix the deposit to 10 months", "Explain lock-in"])

        # Summary / vernacular
        if re.search(r"\b(summar|simple words|plain (english|language)|explain (this|the|my) (agreement|draft|deed)|hindi|kannada|tamil|telugu|translate)\b", low):
            lang = "hi" if "hindi" in low else "kn" if "kannada" in low else "ta" if "tamil" in low else "te" if "telugu" in low else "en"
            s = self._run("summarize_agreement", language=lang)
            text = s.get("summary", "")
            if s.get("note"):
                text += f"\n\n_{s['note']}_"
            return CopilotReply(text=text, suggestions=["Review my clauses for risk", "What will it cost?"])

        # Draft from natural language (numbers or party labels present)
        if re.search(r"\b(draft|create|make|prepare|new agreement|set up|fill|prefill|rent(al)? agreement for|i want to rent|renting)\b", low) or \
                re.search(r"\b(owner|landlord|tenant|lessee|lessor)\b", low) and re.search(r"\d", low):
            ex = self._run("extract_terms_from_text", text=msg, apply=True)
            found = ex.get("fields_found", [])
            if not found:
                return CopilotReply(text="I could not pick out concrete terms. Tell me the city, monthly rent, deposit, duration and the parties' names, "
                                         "for example: 'Rent agreement for Flat 402 Sunrise Apartments, Bellandur, Bangalore. Rent 28,000, deposit 1.2 lakh, 11 months. "
                                         "Owner Ramakiran Reddy 9876543210, tenant Mayank Tripathi 9876543211'.")
            issues = ex.get("remaining_validation_issues", [])
            text = f"I filled the draft with: {', '.join(found)}."
            if issues:
                text += "\n\nStill needed before checkout:\n" + "\n".join(f"- {i}" for i in issues[:8])
                text += "\n\nOpen **Create agreement** to complete these, or tell me the missing details here."
            else:
                text += " Everything validates - open **Create agreement**, review the live preview, then proceed to checkout."
            return CopilotReply(text=text, suggestions=["What will it cost?", "Review my clauses for risk", "Save this as a draft"])

        if re.search(r"\bsave (this|the|my)? ?(draft|agreement)\b", low):
            d = self._run("save_draft")
            if "error" in d:
                return CopilotReply(text=f"Could not save: {d['error']}")
            return CopilotReply(text=f"Saved as draft **{d['title']}** (id {d['agreement_id'][:8]}). Find it under Dashboard > Drafts.")

        # Legal terms / FAQ
        if re.search(r"\b(what is|what's|meaning|explain|define|how does|why do i need|is it (legal|valid)|valid in court|witness|section 65b|e-?stamp|lock-?in|notice period|deposit|escalation|esign|aadhaar|registration)\b", low):
            e = self._run("explain_legal_term", term=msg)
            return CopilotReply(text=e.get("explanation", ""), suggestions=["What will stamp duty cost?", "Draft my agreement"])

        return CopilotReply(text=self._help_text(), suggestions=self._default_suggestions())

    @staticmethod
    def _numbers(low: str) -> Dict[str, float]:
        out: Dict[str, float] = {}
        rent = re.search(r"rent[^\d]{0,25}([\d,.]+)\s*(k|lakh|lakhs|l)?", low)
        dep = re.search(r"(deposit|advance)[^\d]{0,25}([\d,.]+)\s*(k|lakh|lakhs|l)?", low)

        def val(num: str, unit: Optional[str]) -> Optional[float]:
            try:
                v = float(num.replace(",", ""))
            except ValueError:
                return None
            if unit and unit.startswith("l"):
                v *= 100_000
            elif unit == "k":
                v *= 1_000
            return v

        if rent and val(rent.group(1), rent.group(2)):
            out["rent"] = val(rent.group(1), rent.group(2))
        if dep and val(dep.group(2), dep.group(3)):
            out["deposit"] = val(dep.group(2), dep.group(3))
        return out

    @staticmethod
    def _help_text() -> str:
        return ("I'm GoLegal Copilot. I can:\n"
                "- **Draft** an agreement from a sentence (\"2BHK in Bellandur, rent 28k, deposit 1.2L, owner Ramakiran, tenant Mayank\")\n"
                "- **Price** it: stamp duty, platform fee and GST for any state\n"
                "- **Check** fair rent and deposit norms for your locality\n"
                "- **Review** clauses for unfair or unenforceable terms\n"
                "- **Explain** lock-in, e-stamp, Section 65B, witnesses and more, or summarise the deed in simple words or Hindi\n"
                "- **Track** who has signed and re-send signing links\n\n"
                "Payment and Aadhaar eSign stay with you - I will guide you to the right step.")

    @staticmethod
    def _default_suggestions() -> List[str]:
        return ["Draft: 2BHK in Bellandur, rent 28k, deposit 1.2 lakh, owner Ramakiran Reddy, tenant Mayank Tripathi",
                "How much is stamp duty in Maharashtra for rent 40,000?",
                "Is 10 months deposit normal in Bangalore?",
                "Explain Section 65B"]
