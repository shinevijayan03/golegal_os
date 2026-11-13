"""
GoLegal Payment & GST Invoicing Service
Mock Razorpay/Cashfree checkout with webhook-style confirmation and a signed
GST tax invoice archived under the payer's MyInvoices.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from domain.models import Agreement, AuditLog, Payment, User, utc_now
from services.doc_assembly import DocumentAssemblyEngine
from services.document_service import DocumentService
from services.rule_engine import calculate_stamp_duty


class PaymentError(Exception):
    pass


class PaymentService:
    def __init__(self, session: Session):
        self.session = session
        self.documents = DocumentService(session)
        self.engine = DocumentAssemblyEngine()

    def quote(self, agreement: Agreement) -> Dict[str, Any]:
        """Server-side fee computation from the persisted agreement (never from client input)."""
        terms = agreement.get_commercial_terms()
        return calculate_stamp_duty(
            agreement.state_code,
            terms.get("monthly_rent", 0),
            terms.get("security_deposit", 0),
            months=int(terms.get("lease_months", 11) or 11),
        )

    def _next_invoice_number(self) -> str:
        year = utc_now().year
        count = self.session.query(Payment).filter(Payment.invoice_number.isnot(None)).count() + 1
        return f"INV-{year}-{count:05d}"

    def checkout(self, agreement: Agreement, payer: Optional[User], payment_mode: str = "UPI",
                 gateway: str = "Razorpay") -> Payment:
        """Capture payment (mock gateway), issue invoice, journal audit. Idempotent per agreement."""
        existing = self.session.query(Payment).filter_by(agreement_id=agreement.id).first()
        if existing and existing.status == "Success":
            return existing

        quote = self.quote(agreement)
        payment = existing or Payment(agreement_id=agreement.id, gateway_payment_id=f"pay_{uuid.uuid4().hex[:14]}")
        payment.total_amount = quote["total_payable"]
        payment.stamp_duty_amount = quote["stamp_duty_amount"]
        payment.platform_fee = quote["platform_fee"]
        payment.gst_amount = quote["gst_amount"]
        payment.payment_gateway = gateway
        payment.payment_mode = payment_mode
        payment.paid_by_user_id = payer.id if payer else None
        payment.status = "Success"  # gateway webhook `payment.captured` (mock)
        payment.invoice_number = payment.invoice_number or self._next_invoice_number()
        if not existing:
            self.session.add(payment)
        self.session.flush()

        invoice = {
            "invoice_number": payment.invoice_number,
            "issued_at": utc_now(),
            "customer_name": payer.full_name if payer else "GoLegal OS Customer",
            "customer_email": payer.email if payer else "-",
            "agreement_id": agreement.id,
            "gateway": gateway,
            "gateway_payment_id": payment.gateway_payment_id,
            "payment_mode": payment_mode,
            "platform_fee": payment.platform_fee,
            "gst_amount": payment.gst_amount,
            "stamp_duty_amount": payment.stamp_duty_amount,
            "total_amount": payment.total_amount,
            "state_code": agreement.state_code,
        }
        invoice["digest"] = hashlib.sha256(json.dumps(invoice, sort_keys=True, default=str).encode()).hexdigest()
        pdf = self.engine.generate_invoice_pdf(invoice)
        doc = self.documents.store(agreement.id, "INVOICE", f"{payment.invoice_number}.pdf", pdf)
        payment.invoice_pdf_url = f"/documents/{doc.id}"

        self.session.add(AuditLog(
            agreement_id=agreement.id,
            event_type="PAYMENT_CAPTURED",
            triggered_by=f"GATEWAY_{gateway.upper()}",
            event_data=json.dumps({
                "gateway_payment_id": payment.gateway_payment_id,
                "invoice_number": payment.invoice_number,
                "total_amount": payment.total_amount,
                "mode": payment_mode,
                "webhook_event": "payment.captured",
            }),
        ))
        self.session.commit()
        return payment

    def invoices_for_user(self, user: User) -> list[Payment]:
        return (self.session.query(Payment).filter_by(paid_by_user_id=user.id, status="Success")
                .order_by(Payment.created_at.desc()).all())

    def invoice_pdf(self, payment: Payment) -> Optional[bytes]:
        doc = self.documents.latest(payment.agreement_id, "INVOICE")
        return doc.content if doc else None
