"""
GoLegal Document Assembly & Cryptographic Sealing Engine
Uses ReportLab to assemble official e-Stamp Page 1, contract covenants,
two-pass continuous pagination (Page X of Y), Section 65B certificate, and SHA-256 hashing.

The engine is pure: it receives plain dicts and returns bytes, so it is easy to
test and to call from services, the UI, or the AI tool layer.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import settings
from services.rule_engine import AGREEMENT_TYPE_LABELS, STATE_STAMP_RULES

NAVY = colors.HexColor("#1E3A8A")
SLATE = colors.HexColor("#334155")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#CBD5E1")
STAMP_GREEN_BG = colors.HexColor("#E7F3EA")
STAMP_GREEN_FG = colors.HexColor("#1B5E3A")
CRIMSON = colors.HexColor("#B91C1C")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fmt_dt(value: Any, fmt: str = "%d-%b-%Y %H:%M:%S UTC") -> str:
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if value:
        return str(value)
    return "-"


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _esc(value: Any) -> str:
    """Escape user-provided text before it reaches ReportLab's mini-HTML parser."""
    text = "" if value is None else str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and stamp 'Page X of Y' on all pages."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(MUTED)
        if self._pageNumber > 1:
            self.drawString(54, 750, "GoLegal OS Certified Digital Contract - Section 65B Compliant")
            self.setStrokeColor(LINE)
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)
        self.drawRightString(558, 36, f"Page {self._pageNumber} of {page_count}")
        self.drawString(54, 36, "Secured by GoLegal OS Cryptographic Seal (SHA-256)")
        self.setStrokeColor(LINE)
        self.setLineWidth(0.5)
        self.line(54, 48, 558, 48)
        self.restoreState()


class DocumentAssemblyEngine:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._init_custom_styles()

    def _init_custom_styles(self):
        self.title_style = ParagraphStyle("DocTitle", parent=self.styles["Heading1"], fontSize=16, leading=20,
                                          textColor=NAVY, alignment=1, spaceAfter=12)
        self.heading2_style = ParagraphStyle("Heading2Custom", parent=self.styles["Heading2"], fontSize=12,
                                             leading=16, textColor=NAVY, spaceBefore=10, spaceAfter=6)
        self.body_style = ParagraphStyle("BodyCustom", parent=self.styles["Normal"], fontSize=9.5, leading=14,
                                         textColor=colors.HexColor("#1E293B"))
        self.small_style = ParagraphStyle("Small", parent=self.body_style, fontSize=8, leading=11, textColor=MUTED)
        self.cert_banner_style = ParagraphStyle("CertBanner", parent=self.styles["Normal"], fontSize=11,
                                                leading=15, textColor=STAMP_GREEN_FG, alignment=1)
        self.cell_style = ParagraphStyle("Cell", parent=self.body_style, fontSize=7.5, leading=9.5)

    # ------------------------------------------------------------------ seal
    @staticmethod
    def corporate_seal(content_digest: str) -> str:
        """Simulated GoLegal corporate DSC: HMAC-SHA256 over the pre-seal content digest."""
        return hmac.new(settings.dsc_seal_secret.encode(), content_digest.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def content_digest(agreement_data: Dict[str, Any], parties: List[Dict[str, Any]],
                       signatures: Optional[List[Dict[str, Any]]]) -> str:
        """Deterministic digest of the legal content (what the parties actually signed)."""
        import json
        payload = json.dumps({"agreement": agreement_data, "parties": parties,
                              "signatures": [s.get("signature_hash") for s in (signatures or [])]},
                             sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    # ------------------------------------------------------------------ builder
    def generate_pdf_agreement(
        self,
        agreement_data: Dict[str, Any],
        parties: List[Dict[str, Any]],
        estamp: Optional[Dict[str, Any]] = None,
        signatures: Optional[List[Dict[str, Any]]] = None,
        is_draft: bool = False,
        audit: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Build and assemble the complete legal contract PDF into bytes."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54,
                                title=f"GoLegal OS {agreement_data.get('agreement_type', 'Agreement')}",
                                author="GoLegal OS Document Assembly Engine")
        story: List[Any] = []
        audit = audit or {}

        agreement_type = agreement_data.get("agreement_type", "Rental_Residential")
        type_label = AGREEMENT_TYPE_LABELS.get(agreement_type, "Agreement").upper()
        executed_on = agreement_data.get("executed_on") or _now()
        if not isinstance(executed_on, datetime):
            executed_on = _now()
        state = (estamp or {}).get("state_code") or agreement_data.get("state_code", "KA")
        state_name = STATE_STAMP_RULES.get(state, {}).get("name", state)

        owners = [p for p in parties if p.get("type") == "Owner"]
        tenants = [p for p in parties if p.get("type") == "Tenant"]
        witnesses = [p for p in parties if p.get("type") == "Witness"]
        first_party = ", ".join(_esc(p.get("name")) for p in owners) or (_esc(parties[0]["name"]) if parties else "Lessor")
        second_party = ", ".join(_esc(p.get("name")) for p in tenants) or (_esc(parties[1]["name"]) if len(parties) > 1 else "Lessee")

        # ---------------- Page 1: e-Stamp certificate header
        if estamp:
            cert_num = estamp.get("certificate_number", "IN-KA-MOCK-0001")
            duty_amt = float(estamp.get("stamp_amount", 100.0))
            purchaser = estamp.get("purchased_by", "GoLegal OS Platform User")
            issued = _fmt_dt(estamp.get("issued_at"), "%d-%b-%Y %H:%M")
            uid_ref = f"SUBIN-{state}-{cert_num[-10:]}"
        else:
            cert_num, duty_amt, purchaser, issued = "SAMPLE-DRAFT-STAMP", float(agreement_data.get("stamp_duty", 100.0)), "Draft purchaser", "DRAFT"
            uid_ref = f"SUBIN-{state}-DRAFT"
        consideration = float(agreement_data.get("consideration") or (agreement_data.get("monthly_rent", 0) * agreement_data.get("lease_months", 11)))

        stamp_table_data = [
            [Paragraph(f"<b>GOVERNMENT OF {_esc(state_name).upper()} - e-STAMP CERTIFICATE</b>", self.cert_banner_style), ""],
            ["Certificate No:", cert_num],
            ["Certificate Issued Date:", issued],
            ["Account Reference:", f"SHCIL/{state}/GOLEGAL_OS/01"],
            ["Unique Doc Reference:", uid_ref],
            ["Purchased by:", purchaser],
            ["Description of Document:", STATE_STAMP_RULES.get(state, {}).get("article", "Lease")],
            ["Consideration Amount:", f"Rs. {consideration:,.2f}"],
            ["First Party:", first_party],
            ["Second Party:", second_party],
            ["Stamp Duty Paid By:", purchaser],
            ["Stamp Duty Amount:", f"Rs. {duty_amt:,.2f}"],
        ]
        t = Table(stamp_table_data, colWidths=[180, 324])
        t.setStyle(TableStyle([
            ("SPAN", (0, 0), (1, 0)),
            ("BACKGROUND", (0, 0), (1, 0), STAMP_GREEN_BG),
            ("TEXTCOLOR", (0, 0), (1, 0), STAMP_GREEN_FG),
            ("ALIGN", (0, 0), (1, 0), "CENTER"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
            ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#F8FAFC")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 20))

        if is_draft:
            story.append(Paragraph("<b>*** UNEXECUTED DRAFT - FOR PREVIEW PURPOSES ONLY ***</b>",
                                   ParagraphStyle("DraftWM", parent=self.title_style, textColor=CRIMSON)))
            story.append(Spacer(1, 10))

        story.append(Paragraph(f"<b>{type_label}</b>", self.title_style))
        story.append(Paragraph(
            f"This {AGREEMENT_TYPE_LABELS.get(agreement_type, 'agreement')} is made and executed on this "
            f"<b>{_ordinal(executed_on.day)} day of {executed_on.strftime('%B %Y')}</b> at {_esc(agreement_data.get('city', state_name))}, "
            f"between the parties described herein below:", self.body_style))
        story.append(Spacer(1, 10))

        def party_block(label: str, group: List[Dict[str, Any]]):
            for i, party in enumerate(group, 1):
                suffix = f" {i}" if len(group) > 1 else ""
                p_text = (f"<b>{label}{suffix}</b>: <b>{_esc(party.get('name'))}</b>"
                          f"{', PAN: ' + _esc(party['pan']) if party.get('pan') else ''}"
                          f", Contact: {_esc(party.get('phone'))}, Email: {_esc(party.get('email'))}, "
                          f"Aadhaar: {_esc(party.get('aadhaar_masked', 'XXXXXXXXXXXX'))}"
                          f"{', Address: ' + _esc(party['address']) if party.get('address') else ''}.")
                story.append(Paragraph(p_text, self.body_style))
                story.append(Spacer(1, 4))

        if owners or tenants:
            party_block("First Party (Lessor / Owner)", owners)
            party_block("Second Party (Lessee / Tenant)", tenants)
        else:
            for i, party in enumerate(parties):
                party_block(f"{party.get('type', 'Party')} ({'First Party' if i == 0 else 'Second Party'})", [party])
        if witnesses:
            story.append(Paragraph("<b>Attesting Witnesses</b>: " + "; ".join(
                f"{_esc(w.get('name'))} ({_esc(w.get('phone'))})" for w in witnesses), self.body_style))

        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>SCHEDULE OF THE PROPERTY & COMMERCIAL TERMS</b>", self.heading2_style))
        prop_lines = [
            f"<b>Premises Address:</b> {_esc(agreement_data.get('property_address', 'As described in Schedule'))}.",
            f"<b>Monthly Rent:</b> Rs. {float(agreement_data.get('monthly_rent', 0)):,.2f} payable on or before the "
            f"{_ordinal(int(agreement_data.get('rent_due_day', 5)))} of each calendar month.",
            f"<b>Security Deposit:</b> Rs. {float(agreement_data.get('security_deposit', 0)):,.2f} (interest-free, refundable).",
            f"<b>Lease Duration:</b> {agreement_data.get('lease_months', 11)} months commencing {_esc(agreement_data.get('lease_start', 'the date of execution'))}.",
            f"<b>Lock-in Period:</b> {agreement_data.get('lock_in_months', 0)} months. "
            f"<b>Notice Period:</b> {agreement_data.get('notice_days', 30)} days. "
            f"<b>Annual Escalation:</b> {agreement_data.get('escalation_pct', 5)}%.",
        ]
        if agreement_data.get("inclusions"):
            prop_lines.append(f"<b>Fixtures & Inclusions:</b> {_esc(agreement_data['inclusions'])}.")
        story.append(Paragraph("<br/>".join(prop_lines), self.body_style))
        story.append(Spacer(1, 14))

        story.append(Paragraph("<b>TERMS AND COVENANTS</b>", self.heading2_style))
        clauses = agreement_data.get("clauses", [])
        for idx, clause in enumerate(clauses, start=1):
            story.append(Paragraph(f"<b>{idx}. {_esc(clause.get('title', f'Clause {idx}'))}</b>: {_esc(clause.get('text', ''))}", self.body_style))
            story.append(Spacer(1, 6))
        if agreement_data.get("custom_clauses"):
            story.append(Paragraph(f"<b>{len(clauses) + 1}. Additional Covenants agreed between the parties</b>: "
                                   f"{_esc(agreement_data['custom_clauses'])}", self.body_style))

        # ---------------- Section 65B evidentiary page
        story.append(PageBreak())
        story.append(Paragraph("<b>SECTION 65B INDIAN EVIDENCE ACT, 1872 - ELECTRONIC RECORD CERTIFICATE</b>", self.title_style))
        story.append(Paragraph(
            "This document is electronically executed and digitally certified in strict accordance with "
            "Sections 4, 5, and 10A of the Information Technology Act 2000, and Section 65B of the Indian Evidence Act, 1872.",
            self.body_style))
        story.append(Spacer(1, 12))

        sig_rows = [["Party Name", "Role", "Signed At (UTC)", "Signer IP", "PKCS#7 Signature Hash", "Status"]]
        if signatures:
            for s in signatures:
                sig_rows.append([
                    Paragraph(_esc(s.get("party_name", "Signatory")), self.cell_style),
                    s.get("party_type", "Party"),
                    _fmt_dt(s.get("signed_at"), "%d-%b-%Y %H:%M:%S"),
                    s.get("ip_address", "-"),
                    Paragraph(f"{_esc(s.get('signature_hash', ''))[:32]}...", self.cell_style),
                    "Certified",
                ])
        else:
            sig_rows.append(["[Pending Signatures]", "-", "-", "-", "-", "Awaiting Execution"])

        digest = self.content_digest(agreement_data, parties, signatures)
        seal = self.corporate_seal(digest) if signatures and not is_draft else "PENDING-ALL-SIGNATURES"
        sig_rows.append([
            Paragraph("GoLegal OS Corporate DSC", self.cell_style), "Certifying Authority",
            _fmt_dt(audit.get("sealed_at") or executed_on, "%d-%b-%Y %H:%M:%S"),
            audit.get("server_host", socket.gethostname())[:15],
            Paragraph(f"{seal[:32]}...", self.cell_style),
            "Tamper-Proof Sealed" if signatures and not is_draft else "Not yet sealed",
        ])
        sig_table = Table(sig_rows, colWidths=[92, 62, 92, 70, 120, 68])
        sig_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(sig_table)
        story.append(Spacer(1, 14))

        meta_rows = [
            ["System Custodian", f"{settings.company_name} / GoLegal OS Platform"],
            ["Server Host", audit.get("server_host", socket.gethostname())],
            ["Agreement ID", agreement_data.get("agreement_id", "-")],
            ["e-Stamp Certificate", cert_num],
            ["Content Digest (SHA-256)", digest],
            ["Corporate Seal (HMAC-SHA256)", seal],
            ["Certificate Generated (UTC)", _fmt_dt(audit.get("generated_at") or _now())],
        ]
        meta_table = Table([[Paragraph(f"<b>{k}</b>", self.cell_style), Paragraph(_esc(v), self.cell_style)] for k, v in meta_rows],
                           colWidths=[150, 354])
        meta_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 14))

        events = audit.get("events") or []
        if events:
            story.append(Paragraph("<b>Evidentiary Event Log</b>", self.heading2_style))
            ev_rows = [["Recorded (UTC)", "Event", "Actor"]] + [
                [_fmt_dt(e.get("recorded_at"), "%d-%b-%Y %H:%M:%S"), _esc(e.get("event_type", "")), _esc(e.get("triggered_by", ""))[:40]]
                for e in events[:25]
            ]
            ev_table = Table(ev_rows, colWidths=[120, 200, 184])
            ev_table.setStyle(TableStyle([
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(ev_table)
            story.append(Spacer(1, 14))

        story.append(Paragraph(
            "<b>STATUTORY DECLARATION UNDER SECTION 65B(4):</b><br/>"
            "I hereby certify that the electronic contracting record above was produced by the GoLegal OS automated computer "
            "system during its ordinary operational course; that the computer was operating properly throughout; and that the "
            "cryptographic SHA-256 digests, PKCS#7 signature hashes and timestamps above establish unimpaired integrity and non-repudiation.",
            ParagraphStyle("CertDec", parent=self.body_style, fontSize=8.5, textColor=colors.HexColor("#475569"))))

        doc.build(story, canvasmaker=NumberedCanvas)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    # ------------------------------------------------------------------ invoice
    def generate_invoice_pdf(self, invoice: Dict[str, Any]) -> bytes:
        """GST-compliant tax invoice for the platform fee and stamp duty collected."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54,
                                title=f"GoLegal OS Tax Invoice {invoice.get('invoice_number', '')}")
        story: List[Any] = [
            Paragraph("<b>TAX INVOICE</b>", self.title_style),
            Paragraph(f"<b>{_esc(settings.company_name)}</b> - GoLegal OS Digital Contracting<br/>GSTIN: {_esc(settings.company_gstin)} | "
                      f"Place of supply: {_esc(settings.company_state)}<br/>{_esc(settings.support_email)}", self.body_style),
            Spacer(1, 10),
        ]
        head = [
            ["Invoice Number", invoice.get("invoice_number", "-")],
            ["Invoice Date (UTC)", _fmt_dt(invoice.get("issued_at"))],
            ["Billed To", f"{invoice.get('customer_name', '-')} ({invoice.get('customer_email', '-')})"],
            ["Agreement Reference", invoice.get("agreement_id", "-")],
            ["Payment Reference", f"{invoice.get('gateway', 'Razorpay')} / {invoice.get('gateway_payment_id', '-')} ({invoice.get('payment_mode', 'UPI')})"],
        ]
        ht = Table([[Paragraph(f"<b>{k}</b>", self.cell_style), Paragraph(_esc(v), self.cell_style)] for k, v in head], colWidths=[150, 354])
        ht.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINE), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC"))]))
        story += [ht, Spacer(1, 16)]

        fee = float(invoice.get("platform_fee", 0))
        gst = float(invoice.get("gst_amount", 0))
        duty = float(invoice.get("stamp_duty_amount", 0))
        rows = [
            ["#", "Description", "HSN/SAC", "Taxable Value", "GST", "Amount (Rs.)"],
            ["1", "GoLegal OS platform service fee (drafting, e-sign orchestration, sealing)", "998319", f"{fee:,.2f}", f"{gst:,.2f} (18%)", f"{fee + gst:,.2f}"],
            ["2", f"State stamp duty remitted to SHCIL ({invoice.get('state_code', 'KA')}) - pure agent, non-taxable", "-", f"{duty:,.2f}", "0.00", f"{duty:,.2f}"],
            ["", "", "", "", Paragraph("<b>Total Paid</b>", self.cell_style), Paragraph(f"<b>{float(invoice.get('total_amount', fee + gst + duty)):,.2f}</b>", self.cell_style)],
        ]
        lt = Table([[Paragraph(_esc(c), self.cell_style) if isinstance(c, str) else c for c in r] for r in rows],
                   colWidths=[22, 214, 60, 74, 70, 64])
        lt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -2), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (4, -1), (-1, -1), 0.8, NAVY),
        ]))
        story += [lt, Spacer(1, 18),
                  Paragraph("This is a computer-generated invoice digitally signed by GoLegal OS and does not require a physical signature. "
                            "Stamp duty is collected on behalf of the State Government and remitted through Stock Holding Corporation of India Ltd.",
                            self.small_style),
                  Paragraph(f"Invoice digest (SHA-256): {invoice.get('digest', '-')}", self.small_style)]
        doc.build(story, canvasmaker=NumberedCanvas)
        data = buffer.getvalue()
        buffer.close()
        return data

    @staticmethod
    def compute_sha256(pdf_bytes: bytes) -> str:
        """Compute 64-character hexadecimal SHA-256 digest of PDF artifact."""
        return hashlib.sha256(pdf_bytes).hexdigest()

    @staticmethod
    def verify_tamper_evidence(pdf_bytes: bytes, expected_sha256: str) -> bool:
        """Verify that document has not been altered by even 1 bit."""
        return hashlib.sha256(pdf_bytes).hexdigest() == expected_sha256
