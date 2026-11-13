"""
GoLegal Clause Intelligence (PRD 12.2 Phase 2 AI capabilities)

- Clause risk scoring: flags harsh, unusual or unenforceable terms in the
  commercial parameters and free-text covenants.
- Smart PII redaction: masks Aadhaar / PAN / phone numbers that users paste
  into clause text before it is persisted or sent to a model.
- Plain-language and vernacular summaries of the agreement.
- Clause glossary for the Copilot.

Everything works deterministically; when a language model is available the
findings are enriched with model-generated observations.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ai.llm import LLMClient, LLMUnavailableError, extract_json, get_llm_client
from services.rule_engine import get_default_clauses, render_clauses_text

SEVERITY_WEIGHT = {"high": 30, "medium": 12, "low": 5, "info": 0}

AADHAAR_RE = re.compile(r"(?<!\d)(\d{4}[\s-]?\d{4}[\s-]?\d{4})(?!\d)")
PAN_RE = re.compile(r"\b([A-Z]{5}\d{4}[A-Z])\b")
PHONE_RE = re.compile(r"(?<!\d)(\+91[\s-]?)?([6-9]\d{9})(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

RISKY_PATTERNS: List[Dict[str, Any]] = [
    {"id": "FORFEIT_DEPOSIT", "severity": "high", "title": "Deposit forfeiture clause",
     "pattern": r"(forfeit|forfeiture|non[- ]refundable|no refund)[^.]{0,80}(deposit|advance)|(deposit|advance)[^.]{0,80}(forfeit|non[- ]refundable|no refund)",
     "detail": "Blanket forfeiture of the security deposit is routinely struck down as an unenforceable penalty (Contract Act s.74).",
     "suggestion": "Limit deductions to actual, itemised damages and unpaid dues, and set a refund timeline."},
    {"id": "ENTRY_WITHOUT_NOTICE", "severity": "high", "title": "Owner entry without notice",
     "pattern": r"(enter|inspect|access)[^.]{0,60}(any ?time|without (prior )?notice|at will)",
     "detail": "Unrestricted entry defeats the tenant's right to peaceful enjoyment and invites disputes.",
     "suggestion": "Require at least 24 hours' notice except in emergencies."},
    {"id": "WAIVER_OF_NOTICE", "severity": "high", "title": "Eviction without notice",
     "pattern": r"(vacate|evict|terminate)[^.]{0,60}(immediately|without (any )?notice|no notice)",
     "detail": "Termination without notice conflicts with the agreed notice clause and most state rent laws.",
     "suggestion": "Use the notice period already defined in the agreement for both sides."},
    {"id": "EXCESSIVE_PENALTY", "severity": "medium", "title": "Punitive late-payment penalty",
     "pattern": r"(penalty|fine|interest)[^.]{0,40}(\d{2,3}\s?%|₹\s?\d{4,}|rs\.?\s?\d{4,})",
     "detail": "Penalties far above actual loss are generally unenforceable and hurt trust.",
     "suggestion": "Cap late fees at a modest daily rate (for example ₹100/day) or 1–2% per month."},
    {"id": "UNILATERAL_CHANGE", "severity": "medium", "title": "One-sided right to change terms",
     "pattern": r"(owner|lessor|landlord)[^.]{0,60}(sole discretion|at (his|her|their) discretion|may (change|modify|alter|revise)[^.]{0,30}(terms|rent))",
     "detail": "A term one party can change unilaterally is unlikely to bind the other party.",
     "suggestion": "Make changes mutual and in writing."},
    {"id": "LIABILITY_WAIVER", "severity": "medium", "title": "Blanket liability waiver",
     "pattern": r"(not (be )?(liable|responsible)|no liability)[^.]{0,80}(any|all)[^.]{0,30}(loss|damage|injury)",
     "detail": "Blanket waivers rarely survive scrutiny and can void the clause entirely.",
     "suggestion": "Limit to losses caused by the other party's own negligence."},
    {"id": "RELIGION_CASTE_FOOD", "severity": "medium", "title": "Discriminatory or personal-conduct restriction",
     "pattern": r"\b(caste|religion|religious|communit(?:y|ies)|non[- ]?veg\w*|vegetarians?|bachelors?|spinsters?|unmarried|marital status|gender|men only|women only)\b",
     "detail": "Restrictions on food habits, marital status or community are legally fragile and reputationally risky.",
     "suggestion": "Replace with neutral house rules on noise, nuisance and guests."},
    {"id": "SUBLET_BLANKET", "severity": "info", "title": "Subletting addressed",
     "pattern": r"\bsub-?let",
     "detail": "Subletting is already covered by the standard clause toggle; keep only one definition.",
     "suggestion": "Use the 'Subletting permitted' toggle instead of free text."},
    {"id": "VERBAL_TERMS", "severity": "low", "title": "Reference to verbal or side agreements",
     "pattern": r"\b(verbal|oral)[^.]{0,30}(agreement|understanding|promise)",
     "detail": "Unwritten terms are not evidenced by the deed and cannot be relied upon under Section 65B.",
     "suggestion": "Write every agreed term into the deed."},
]

CLAUSE_GLOSSARY: Dict[str, str] = {
    "lock-in": "A lock-in period is the minimum time both sides commit to the tenancy. Leaving early usually means paying rent for the remaining lock-in months.",
    "notice period": "The written notice either side must give before ending the agreement. 30 days is standard for residential rentals in India.",
    "security deposit": "A refundable amount held by the owner against unpaid dues or damage. It must be returned (less lawful deductions) when you vacate; Karnataka commonly sees 5–10 months, Delhi 2–3.",
    "escalation": "The percentage by which rent increases on renewal, typically 5% or 10% per year.",
    "e-stamp": "An electronic stamp paper issued by Stock Holding Corporation of India (SHCIL). It proves state stamp duty was paid and is what makes the deed admissible as evidence.",
    "stamp duty": "A state tax on legal instruments. Karnataka and Delhi charge a flat ₹100 for 11-month rentals; Maharashtra charges 0.25% of the total consideration for leave and licence.",
    "aadhaar esign": "A legally recognised electronic signature under the IT Act 2000 where a licensed Certifying Authority issues a one-time certificate after Aadhaar OTP verification. GoLegal OS never stores your full Aadhaar number.",
    "section 65b": "Section 65B of the Indian Evidence Act lets electronic records be produced in court when accompanied by a certificate describing how they were generated. GoLegal OS appends this certificate to every sealed deed.",
    "witness": "Witnesses attest that the parties signed. Rental agreements usually have two. Witnesses only sign; they do not receive a copy of the executed deed on GoLegal OS.",
    "leave and licence": "Maharashtra's form of rental arrangement: a licence to occupy rather than a lease. It must be registered and stamped under Article 36A.",
    "peaceful enjoyment": "The tenant's right to use the premises without interference from the owner, who must give notice before visiting.",
    "painting deduction": "A customary deduction (often one month's rent) from the deposit to repaint the premises when the tenant vacates.",
    "consideration": "The total value of the contract, here total rent for the term plus notional interest on the deposit, used to compute stamp duty in percentage-based states.",
    "sublet": "Renting out part or all of the premises to someone else. Standard agreements prohibit it without written consent.",
}


@dataclass
class RiskFinding:
    id: str
    severity: str
    title: str
    detail: str
    suggestion: str
    quote: str = ""
    source: str = "rules"


@dataclass
class RiskReport:
    score: int
    level: str
    findings: List[RiskFinding] = field(default_factory=list)
    summary: str = ""
    redacted_text: Optional[str] = None
    pii_redactions: int = 0
    model: str = "rule-based"

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "findings": [asdict(f) for f in self.findings]}


def redact_pii(text: str) -> tuple[str, int]:
    """Mask Aadhaar, PAN and phone numbers in free text. Returns (clean_text, count)."""
    if not text:
        return "", 0
    count = 0

    def _aadhaar(m):
        nonlocal count
        count += 1
        digits = re.sub(r"\D", "", m.group(1))
        return f"XXXXXXXX{digits[-4:]}"

    def _pan(m):
        nonlocal count
        count += 1
        return f"{m.group(1)[:2]}XXXXXX{m.group(1)[-2:]}"

    def _phone(m):
        nonlocal count
        count += 1
        return f"XXXXXX{m.group(2)[-4:]}"

    clean = AADHAAR_RE.sub(_aadhaar, text)
    clean = PAN_RE.sub(_pan, clean)
    clean = PHONE_RE.sub(_phone, clean)
    return clean, count


class ClauseIntelligence:
    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or get_llm_client()

    # ------------------------------------------------------------------ risk
    def assess_risk(self, custom_text: str, commercials: Dict[str, Any], toggles: Optional[Dict[str, bool]] = None,
                    agreement_type: str = "Rental_Residential", state_code: str = "KA",
                    use_llm: bool = True) -> RiskReport:
        findings: List[RiskFinding] = []
        custom_text = custom_text or ""
        rent = float(commercials.get("monthly_rent") or 0)
        deposit = float(commercials.get("security_deposit") or 0)
        lease = int(commercials.get("lease_months") or 11)
        lock_in = int(commercials.get("lock_in_months") or 0)
        notice = int(commercials.get("notice_days") or 30)
        escalation = float(commercials.get("escalation_pct") or 0)

        # Commercial parameter rules
        if rent > 0 and deposit > 10 * rent:
            findings.append(RiskFinding("DEPOSIT_EXCESSIVE", "high", "Security deposit above 10 months' rent",
                                        f"Deposit is {deposit / rent:.1f}× the monthly rent. Karnataka's Model Tenancy norms cap deposits at 10 months; other states at 2–3.",
                                        "Negotiate the deposit down or document a clear refund timeline."))
        elif rent > 0 and deposit > 6 * rent and state_code not in ("KA", "TN"):
            findings.append(RiskFinding("DEPOSIT_HIGH", "medium", "Security deposit above local norm",
                                        f"Deposit is {deposit / rent:.1f}× rent; {state_code} norms are typically 2–3 months.",
                                        "Consider aligning with the local norm."))
        if lock_in > lease:
            findings.append(RiskFinding("LOCKIN_GT_LEASE", "high", "Lock-in longer than the lease",
                                        "A lock-in that outlasts the term is contradictory and unenforceable.",
                                        "Set lock-in to at most the lease duration (6 months is common)."))
        elif lease and lock_in > max(6, lease * 0.75):
            findings.append(RiskFinding("LOCKIN_LONG", "medium", "Long lock-in period",
                                        f"{lock_in} months of lock-in on a {lease}-month term restricts the tenant's exit.",
                                        "6 months is customary for 11-month residential deeds."))
        if notice < 15:
            findings.append(RiskFinding("NOTICE_SHORT", "medium", "Very short notice period",
                                        f"{notice} days gives either side little time to re-let or relocate.",
                                        "30 days is the accepted standard."))
        elif notice > 90:
            findings.append(RiskFinding("NOTICE_LONG", "medium", "Unusually long notice period",
                                        f"{notice} days of notice is onerous for a residential tenant.",
                                        "30–60 days is customary."))
        if escalation > 20:
            findings.append(RiskFinding("ESCALATION_HIGH", "high", "Rent escalation above 20%",
                                        f"{escalation:.0f}% annual escalation is far above the 5–10% market norm.",
                                        "Use 5% or 10%."))
        elif escalation > 10:
            findings.append(RiskFinding("ESCALATION_ABOVE_NORM", "low", "Rent escalation above 10%",
                                        f"{escalation:.0f}% annual escalation exceeds the usual 5–10%.",
                                        "Consider 10% or less."))
        if agreement_type == "Rental_Residential" and lease > 11:
            findings.append(RiskFinding("REGISTRATION_REQUIRED", "info", "Lease of 12 months or more needs registration",
                                        "Leases of one year or longer must be registered with the Sub-Registrar (Registration Act s.17); e-stamping alone is not enough.",
                                        "Keep residential tenancies at 11 months or plan for registration."))

        # Free-text covenant rules
        clean_text, pii_count = redact_pii(custom_text)
        if pii_count:
            findings.append(RiskFinding("PII_IN_CLAUSE", "high", "Personal identifiers in clause text",
                                        f"{pii_count} Aadhaar/PAN/phone value(s) were found in the custom covenants. Identity numbers belong in the party records, masked, not in the deed body.",
                                        "GoLegal OS has masked them. Remove them from the clause text.",
                                        source="pii-scan"))
        lowered = custom_text.lower()
        for rule in RISKY_PATTERNS:
            m = re.search(rule["pattern"], lowered, flags=re.IGNORECASE)
            if m:
                start = max(0, m.start() - 20)
                quote = custom_text[start:m.end() + 20].strip()
                findings.append(RiskFinding(rule["id"], rule["severity"], rule["title"], rule["detail"],
                                            rule["suggestion"], quote=quote))

        model_name = "rule-based"
        if use_llm and self.llm.available and custom_text.strip():
            try:
                findings += self._llm_findings(custom_text, commercials, agreement_type)
                model_name = self.llm.model
            except LLMUnavailableError:
                pass

        score = min(100, sum(SEVERITY_WEIGHT.get(f.severity, 0) for f in findings))
        level = "high" if score >= 40 else "medium" if score >= 15 else "low"
        summary = self._summarise(findings, level)
        return RiskReport(score=score, level=level, findings=findings, summary=summary,
                          redacted_text=clean_text if pii_count else None, pii_redactions=pii_count, model=model_name)

    def _llm_findings(self, custom_text: str, commercials: Dict[str, Any], agreement_type: str) -> List[RiskFinding]:
        system = ("You are a senior Indian property lawyer reviewing custom covenants in a residential rental deed. "
                  "Return ONLY a JSON array of findings: [{\"id\": str, \"severity\": \"high|medium|low|info\", "
                  "\"title\": str, \"detail\": str, \"suggestion\": str, \"quote\": str}]. Flag only genuinely "
                  "unfair, unenforceable or ambiguous terms. Do not repeat parameter checks on deposit, lock-in, "
                  "notice or escalation - those are handled separately. Return [] when nothing is wrong.")
        user = f"Agreement type: {agreement_type}\nCommercial terms: {commercials}\n\nCustom covenants:\n{custom_text}"
        resp = self.llm.complete(system, [{"role": "user", "content": user}], max_tokens=1500)
        data = extract_json(resp.text) or []
        out = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            out.append(RiskFinding(
                id=f"LLM_{str(item.get('id', 'FINDING')).upper()[:30]}",
                severity=item.get("severity", "low") if item.get("severity") in SEVERITY_WEIGHT else "low",
                title=str(item["title"])[:120], detail=str(item.get("detail", ""))[:500],
                suggestion=str(item.get("suggestion", ""))[:300], quote=str(item.get("quote", ""))[:200], source="claude",
            ))
        return out

    @staticmethod
    def _summarise(findings: List[RiskFinding], level: str) -> str:
        if not findings:
            return "No risk signals. The terms are within customary Indian residential norms."
        highs = [f.title for f in findings if f.severity == "high"]
        meds = [f.title for f in findings if f.severity == "medium"]
        parts = []
        if highs:
            parts.append(f"{len(highs)} high-risk item(s): {', '.join(highs)}")
        if meds:
            parts.append(f"{len(meds)} item(s) worth revisiting: {', '.join(meds)}")
        if not parts:
            parts.append("Only informational notes.")
        return f"Overall risk {level.upper()}. " + ". ".join(parts) + "."

    # ------------------------------------------------------------------ summaries
    def plain_language_summary(self, payload: Dict[str, Any], language: str = "en") -> Dict[str, Any]:
        """Explain the agreement in simple terms. English is deterministic; Hindi/Kannada need the model."""
        owners = ", ".join(o.get("name", "") for o in payload.get("owners", []) if o.get("name")) or "the owner"
        tenants = ", ".join(t.get("name", "") for t in payload.get("tenants", []) if t.get("name")) or "the tenant"
        prop = payload.get("property", {})
        c = payload.get("commercials", {})
        toggles = payload.get("clause_toggles", {})
        clauses = get_default_clauses(toggles, payload.get("agreement_type", "Rental_Residential"))
        rent = float(c.get("monthly_rent") or 0)
        deposit = float(c.get("security_deposit") or 0)
        lines = [
            f"{owners} is renting {prop.get('premises_name') or 'the premises'} at {prop.get('address', '')}, {prop.get('city', '')} to {tenants}.",
            f"Rent is ₹{rent:,.0f} every month, due by the {c.get('rent_due_day', 5)}th. The refundable deposit is ₹{deposit:,.0f}"
            + (f" ({deposit / rent:.1f} months of rent)." if rent else "."),
            f"The agreement runs {c.get('lease_months', 11)} months with a {c.get('lock_in_months', 0)}-month lock-in. "
            f"Either side can end it with {c.get('notice_days', 30)} days' written notice. Rent rises {c.get('escalation_pct', 5)}% on renewal.",
            "Pets are " + ("allowed." if toggles.get("pets_allowed") else "not allowed without written permission."),
            "Subletting is " + ("allowed with consent." if toggles.get("subletting_allowed") else "not allowed."),
            ("A standard painting charge will be deducted from the deposit when you leave. " if toggles.get("painting_deduction", True) else "")
            + "Deposit must be refunded within 30 days of handing back the keys, minus lawful deductions.",
            "The deed is executed on government e-stamp paper and signed with Aadhaar eSign, so it is valid in Indian courts.",
        ]
        if payload.get("custom_clauses"):
            lines.append(f"Additional house rules agreed: {payload['custom_clauses'].strip()}")
        english = " ".join(lines)
        result = {"language": "en", "summary": english, "model": "rule-based", "clause_count": len(clauses)}
        if language != "en":
            if self.llm.available:
                lang_name = {"hi": "Hindi", "kn": "Kannada", "ta": "Tamil", "te": "Telugu"}.get(language, language)
                try:
                    resp = self.llm.complete(
                        f"Translate the following rental agreement summary into simple, respectful {lang_name} for a non-technical property owner. Keep numbers in digits. Return only the translation.",
                        [{"role": "user", "content": english}], max_tokens=1500)
                    result.update({"language": language, "summary": resp.text, "model": self.llm.model})
                except LLMUnavailableError:
                    result["note"] = "Translation service unavailable; showing English."
            else:
                result["note"] = "Vernacular summaries need the AI service (set ANTHROPIC_API_KEY). Showing English."
        return result

    def explain_clause(self, query: str) -> str:
        q = (query or "").lower()
        for key, text in CLAUSE_GLOSSARY.items():
            if key in q:
                return text
        # match clause titles from the library
        for clause in get_default_clauses():
            if clause["title"].lower() in q or any(w in q for w in clause["title"].lower().split()[:1]):
                return f"{clause['title']}: {clause['text']}"
        if self.llm.available:
            try:
                resp = self.llm.complete(
                    "You are GoLegal OS's contract assistant for Indian residential rentals. Explain the term in two or three plain sentences. No legal advice disclaimers.",
                    [{"role": "user", "content": query}], max_tokens=400)
                return resp.text
            except LLMUnavailableError:
                pass
        return ("I can explain these terms: " + ", ".join(sorted(CLAUSE_GLOSSARY)) + ". Ask about any of them.")

    def clause_text(self, payload: Dict[str, Any]) -> str:
        return render_clauses_text(get_default_clauses(payload.get("clause_toggles"), payload.get("agreement_type", "Rental_Residential")),
                                   payload.get("custom_clauses", ""))
