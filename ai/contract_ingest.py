"""
GoLegal Contract Ingestion (PRD 5.1 - OCR digitisation of existing contracts)

Turns an existing agreement (pasted text, PDF, or a natural-language brief
typed into the Copilot) into a partial wizard payload. A deterministic
regex extractor always runs; when a model is available it performs a
structured extraction and the two are merged (model wins on conflicts,
regex fills the gaps).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai.llm import LLMClient, LLMUnavailableError, extract_json, get_llm_client
from ai.rent_benchmark import CITY_ALIASES, MICRO_MARKET
from services.rule_engine import STATE_STAMP_RULES

MONEY = r"(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(lakhs?|lacs?|l\b|k\b|thousand)?"
PARTY_LABELS = {
    "owners": r"(?:owner|lessor|landlord|licensor|first party)",
    "tenants": r"(?:tenant|lessee|licensee|second party|co-?tenant|roommate|flatmate)",
    "witnesses": r"(?:witness(?:es)?)",
}
NAME = r"((?:[A-Z][a-zA-Z.'-]+)(?:\s+(?:[A-Z][a-zA-Z.'-]+)){0,3})"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+91[\s-]?)?([6-9]\d{9})(?!\d)")
PAN_RE = re.compile(r"\b([A-Z]{5}\d{4}[A-Z])\b")
AADHAAR_RE = re.compile(r"(?<!\d)(\d{4}[\s-]?\d{4}[\s-]?\d{4})(?!\d)")
PIN_RE = re.compile(r"(?<!\d)([1-9]\d{5})(?!\d)")


def parse_money(num: str, unit: Optional[str]) -> Optional[float]:
    try:
        value = float(num.replace(",", ""))
    except ValueError:
        return None
    unit = (unit or "").lower()
    if unit.startswith("l"):
        value *= 100_000
    elif unit in ("k", "thousand"):
        value *= 1_000
    return value


@dataclass
class IngestResult:
    payload_updates: Dict[str, Any] = field(default_factory=dict)
    fields_found: List[str] = field(default_factory=list)
    confidence: float = 0.0
    notes: List[str] = field(default_factory=list)
    model: str = "rule-based"

    def to_dict(self) -> Dict[str, Any]:
        return {"payload_updates": self.payload_updates, "fields_found": self.fields_found,
                "confidence": self.confidence, "notes": self.notes, "model": self.model}


def extract_text_from_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        return ""
    import io
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def _first_money(text: str, label_pattern: str, window: int = 60, min_value: float = 1000) -> Optional[float]:
    """First money amount near a label, skipping small numbers such as flat numbers ("Flat 402")."""
    for m in re.finditer(label_pattern + r"[^\d₹]{0," + str(window) + r"}" + MONEY, text, flags=re.IGNORECASE):
        val = parse_money(m.group(1), m.group(2))
        if val and val >= min_value:
            return val
    # money before label ("28,000 per month rent")
    for m in re.finditer(MONEY + r"[^\n.]{0,25}" + label_pattern, text, flags=re.IGNORECASE):
        val = parse_money(m.group(1), m.group(2))
        if val and val >= min_value:
            return val
    return None


def _party_block(text: str, label_regex: str) -> List[Dict[str, str]]:
    """Find 'Owner: Name ...' style mentions and harvest contact details from the following text."""
    people: List[Dict[str, str]] = []
    pattern = re.compile(label_regex + r"\s*(?:is|:|-|named|name|=)?\s*(?:mr\.?|mrs\.?|ms\.?|dr\.?|shri|smt\.?)?\s*" + NAME, re.IGNORECASE)
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        if name.lower() in {"name", "the", "and", "of", "is", "shall", "will", "details", "information"}:
            continue
        if len(name) < 3 or any(w.lower() in {"agreement", "party", "phone", "email", "aadhaar", "pan"} for w in name.split()):
            continue
        tail = text[m.end(): m.end() + 220]
        entry = {"name": name}
        email = EMAIL_RE.search(tail)
        phone = PHONE_RE.search(tail)
        pan = PAN_RE.search(tail)
        aadhaar = AADHAAR_RE.search(tail)
        if email:
            entry["email"] = email.group(0)
        if phone:
            entry["phone"] = phone.group(1)
        if pan:
            entry["pan"] = pan.group(1)
        if aadhaar:
            entry["aadhaar"] = re.sub(r"\D", "", aadhaar.group(1))
        if not any(p["name"].lower() == name.lower() for p in people):
            people.append(entry)
    return people


PREMISES_RE = re.compile(
    r"(?:(?P<kind>flat|apartments?|apt|house|villa|door|unit|premises|plot)\s*(?:no\.?|number|#)?\s*(?P<num1>[A-Za-z]?-?\d{1,4}[A-Za-z]?)"
    r"|(?P<name>[A-Z][\w'&.-]*(?:\s+[A-Z][\w'&.-]*){0,3}\s+(?:Apartments?|Residency|Enclave|Towers?|Heights|Villa|Nagar|Layout|Complex|Manor|Court))"
    r"\s*(?:,?\s*(?:flat|apt|unit|no\.?|#)?\s*(?P<num2>[A-Za-z]?-?\d{1,4}[A-Za-z]?))?)",
    re.IGNORECASE)


LEAD_NOISE = re.compile(
    r"^(?:draft\s*:?|rent(?:al)?\s+agreement\s+(?:for|of)|lease\s+(?:of|for)|agreement\s+(?:for|of)|"
    r"i\s+want\s+to\s+(?:rent|lease)(?:\s+out)?(?:\s+my)?|renting\s+out|please\s+draft|create|make|"
    r"premises\s+(?:at|in)|property\s+(?:at|in)|for|the|my|a|an)\s+", re.IGNORECASE)
LOCATIVE = re.compile(r"\b(?:situated\s+at|located\s+at|located\s+in|at|in|near)\s+(?P<tail>.{3,})$", re.IGNORECASE)
TERM_WORDS = re.compile(r"\b(rent|deposit|advance|month|notice|lock[\s-]?in|escalation|owner|lessor|tenant|lessee|witness|pan|aadhaar)\b",
                        re.IGNORECASE)
NAME_STOPWORDS = re.compile(r"^(?:\d\s*-?\s*bhk|bhk|at|in|of|for|the|my|a|an|is|and)\s+", re.IGNORECASE)


def _clean_address_chunk(chunk: str) -> str:
    cleaned = LEAD_NOISE.sub("", chunk.strip(" .;")).strip()
    loc = LOCATIVE.search(cleaned)
    if loc:
        cleaned = loc.group("tail").strip()
    cleaned = re.sub(r"^\d\s*-?\s*bhk\b\s*", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned.strip(" ,.")


def _extract_location(text: str, city: str, pincode: str) -> tuple[str, str]:
    """Return (premises_name, street_address).

    Comma-separated chunks are the natural shape of an Indian address, so this
    anchors on the chunk naming the city (or carrying the PIN code) and reads
    the premises and locality backwards from there. That is far more reliable
    across phrasings than one large regex.
    """
    premises, address = "", ""
    m = PREMISES_RE.search(text)
    if m:
        num = (m.group("num2") or m.group("num1") or "").strip()
        name = m.group("name") or ""
        while name and NAME_STOPWORDS.match(name):
            name = NAME_STOPWORDS.sub("", name, count=1)
        generic = {"villa", "apartment", "apartments", "house", "flat", "premises", "plot", "unit", "towers", "tower"}
        if name.strip() and not (name.strip().lower() in generic and not num):
            premises = name.strip() + (f", {num}" if num else "")
        elif num and m.group("kind"):
            premises = f"{m.group('kind').title().rstrip('s')} {num}"

    chunks = [ch for ch in (c.strip(" .;") for c in re.split(r"[,\n]", text)) if ch]
    anchor = next((i for i, ch in enumerate(chunks)
                   if (city and city.lower() in ch.lower()) or (pincode and pincode in ch)), -1)
    parts = []
    if anchor > 0:
        for ch in chunks[max(0, anchor - 2):anchor]:
            cleaned = _clean_address_chunk(ch)
            if cleaned and not TERM_WORDS.search(cleaned):
                parts.append(cleaned)
    # Drop the chunk that merely repeats the premises we already captured.
    num_match = re.search(r"\d{1,4}", premises or "")
    if parts and premises and num_match and num_match.group(0) in parts[0] and len(parts[0]) <= 40:
        parts = parts[1:]
    elif parts and premises and premises.split(",")[0].lower() in parts[0].lower():
        parts = parts[1:]
    address = ", ".join(parts).strip(", ")
    if not address and anchor >= 0:
        fallback = _clean_address_chunk(re.sub(r"\b\d{6}\b", "", chunks[anchor]))
        if city and fallback.lower() != city.lower() and not TERM_WORDS.search(fallback):
            address = fallback
    return premises, address


def extract_terms_rule_based(text: str) -> IngestResult:
    res = IngestResult()
    if not text or not text.strip():
        return res
    t = text.replace("₹", "₹")
    updates: Dict[str, Any] = {"commercials": {}, "property": {}}

    rent = _first_money(t, r"(?:monthly\s+)?rent(?:al)?(?:\s+of|\s+is|\s+at|\s*:|\s*=|\s+amount)?")
    if rent:
        updates["commercials"]["monthly_rent"] = int(rent)
        res.fields_found.append("monthly_rent")
    deposit = _first_money(t, r"(?:security\s+)?(?:deposit|advance)(?:\s+of|\s+is|\s*:|\s*=|\s+amount)?", min_value=500)
    if deposit:
        updates["commercials"]["security_deposit"] = int(deposit)
        res.fields_found.append("security_deposit")

    m = re.search(r"(\d{1,2})[\s-]*months?", t, flags=re.IGNORECASE)
    if m and 1 <= int(m.group(1)) <= 60:
        updates["commercials"]["lease_months"] = int(m.group(1))
        res.fields_found.append("lease_months")
    m = re.search(r"lock[\s-]*in[^\d]{0,25}(\d{1,2})", t, flags=re.IGNORECASE)
    if m:
        updates["commercials"]["lock_in_months"] = int(m.group(1))
        res.fields_found.append("lock_in_months")
    m = re.search(r"notice[^\d]{0,30}(\d{1,3})\s*days?", t, flags=re.IGNORECASE) or re.search(r"(\d{1,3})\s*days?[^.]{0,20}notice", t, flags=re.IGNORECASE)
    if m:
        updates["commercials"]["notice_days"] = int(m.group(1))
        res.fields_found.append("notice_days")
    m = re.search(r"(\d{1,2}(?:\.\d)?)\s*%[^.\n]{0,40}(?:escalat|increase|hike|increment)", t, flags=re.IGNORECASE) or \
        re.search(r"(?:escalat|increase|hike|increment)[^\d.\n]{0,40}(\d{1,2}(?:\.\d)?)\s*%", t, flags=re.IGNORECASE)
    if m:
        updates["commercials"]["escalation_pct"] = float(m.group(1))
        res.fields_found.append("escalation_pct")
    m = re.search(r"(?:from|commenc\w+|starting|w\.e\.f\.?)\s*(?:on\s+)?(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})", t, flags=re.IGNORECASE)
    if m:
        updates["commercials"]["lease_start"] = m.group(1)
        res.fields_found.append("lease_start")

    pin = PIN_RE.search(t)
    if pin:
        updates["property"]["pincode"] = pin.group(1)
        res.fields_found.append("pincode")
    for code, rule in STATE_STAMP_RULES.items():
        if re.search(r"\b" + re.escape(rule["name"]) + r"\b", t, flags=re.IGNORECASE):
            updates["state_code"] = code
            res.fields_found.append("state_code")
            break
    low = t.lower()
    for alias, canon in list(CITY_ALIASES.items()) + [(c, c) for c in MICRO_MARKET]:
        if re.search(r"\b" + re.escape(alias) + r"\b", low):
            updates["property"]["city"] = canon.title()
            res.fields_found.append("city")
            if "state_code" not in updates:
                updates["state_code"] = {"bangalore": "KA", "delhi": "DL", "gurgaon": "HR", "mumbai": "MH", "pune": "MH",
                                         "hyderabad": "TS", "chennai": "TN"}.get(canon, "KA")
            break
    premises, address = _extract_location(t, updates["property"].get("city", ""), updates["property"].get("pincode", ""))
    if premises:
        updates["property"]["premises_name"] = premises
        res.fields_found.append("premises_name")
    if address:
        updates["property"]["address"] = address
        res.fields_found.append("address")
    m = re.search(r"\b([1-4])\s*-?\s*bhk\b", t, flags=re.IGNORECASE)
    if m:
        updates["property"]["property_type"] = f"{m.group(1)}BHK Apartment"
        res.fields_found.append("property_type")

    for key, label in PARTY_LABELS.items():
        people = _party_block(t, label)
        if people:
            updates[key] = people
            res.fields_found.append(key)

    updates = {k: v for k, v in updates.items() if v not in ({}, [], None)}
    res.payload_updates = updates
    expected = 9
    res.confidence = round(min(1.0, len(set(res.fields_found)) / expected), 2)
    if not res.fields_found:
        res.notes.append("No recognisable rental terms found. Try including rent, deposit, duration, city and party names.")
    return res


LLM_SCHEMA_HINT = """Return ONLY JSON with this shape (omit unknown keys):
{"agreement_type": "Rental_Residential|Rental_Commercial|NDA|Custom", "state_code": "KA|DL|MH|TN|TS|GJ|WB|HR|UP",
 "owners": [{"name": "", "phone": "", "email": "", "pan": "", "address": ""}],
 "tenants": [{"name": "", "phone": "", "email": "", "pan": "", "address": ""}],
 "witnesses": [{"name": "", "phone": "", "email": ""}],
 "property": {"premises_name": "", "address": "", "city": "", "pincode": "", "property_type": "", "inclusions": ""},
 "commercials": {"monthly_rent": 0, "security_deposit": 0, "lease_months": 11, "lock_in_months": 0, "notice_days": 30,
                 "rent_due_day": 5, "escalation_pct": 5, "lease_start": ""},
 "custom_clauses": ""}
Never include Aadhaar numbers; if present, drop them."""


def extract_terms(text: str, llm: Optional[LLMClient] = None, use_llm: bool = True) -> IngestResult:
    """Rule-based extraction, enriched by the model when configured."""
    result = extract_terms_rule_based(text)
    llm = llm or get_llm_client()
    if use_llm and llm.available and text and text.strip():
        try:
            resp = llm.complete(
                "You extract structured rental agreement terms from Indian contracts or plain-English briefs. " + LLM_SCHEMA_HINT,
                [{"role": "user", "content": text[:20000]}], max_tokens=2000)
            data = extract_json(resp.text)
            if isinstance(data, dict):
                merged = dict(result.payload_updates)
                for k, v in data.items():
                    if v in ("", None, [], {}):
                        continue
                    if isinstance(v, dict) and isinstance(merged.get(k), dict):
                        merged[k] = {**merged[k], **{kk: vv for kk, vv in v.items() if vv not in ("", None)}}
                    else:
                        merged[k] = v
                for group in ("owners", "tenants", "witnesses"):
                    for p in merged.get(group, []) or []:
                        p.pop("aadhaar", None)
                result.payload_updates = merged
                result.fields_found = sorted(set(result.fields_found) | {k for k in data if data[k] not in ("", None, [], {})})
                result.confidence = round(min(1.0, max(result.confidence, len(result.fields_found) / 9)), 2)
                result.model = llm.model
        except LLMUnavailableError:
            result.notes.append("Model extraction unavailable; used rule-based extraction only.")
    return result


def merge_into_payload(payload: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge extracted updates into a wizard payload (lists replace, dicts merge)."""
    out = dict(payload)
    for k, v in (updates or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        elif isinstance(v, list) and k in ("owners", "tenants", "witnesses"):
            template = {"name": "", "phone": "", "email": "", "pan": "", "aadhaar": "", "address": ""}
            out[k] = [{**template, **{kk: str(vv) for kk, vv in item.items() if vv is not None}} for item in v if isinstance(item, dict)]
        else:
            out[k] = v
    return out
